package dev.asu.erp;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** Maps API fields onto eight relational business tables. No caller-controlled SQL identifiers. */
@Repository
public class RecordRepository {
    enum SqlType { TEXT, INTEGER, DECIMAL, DATETIME, DATE }
    record Column(String name,SqlType type) {}
    record Table(String name,LinkedHashMap<String,Column> columns) {}
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private static final TypeReference<LinkedHashMap<String,Object>> TYPE = new TypeReference<>() {};
    private static final Map<String,Table> TABLES = Map.of(
        "users", table("erp_user", "username:t,displayName:t,status:i"),
        "suppliers", table("erp_supplier", "supplierCode:t,name:t,status:i,creditRating:t,contactPerson:t,email:t,address:t"),
        "parts", table("erp_part", "partCode:t,name:t,category:t,supplierId:i,price:d,unit:t,status:i,specification:t"),
        "orders", table("erp_purchase_order", "orderNumber:t,totalAmount:d,status:i,orderTime:dt,expectedDeliveryDate:date,actualDeliveryDate:date,createdBy:i,remark:t"),
        "inventory", table("erp_inventory", "partId:i,quantity:i,safetyStock:i,warehouseLocation:t,lastInboundTime:dt,lastOutboundTime:dt"),
        "customers", table("erp_customer", "customerCode:t,name:t,customerType:i,discountRate:d"),
        "logistics", table("erp_logistics", "logisticsNumber:t,orderId:i,status:i,logisticsCompany:t,trackingNumber:t,shippingDate:date,receivingDate:date,receiver:t,remark:t")
    );
    private static final LinkedHashMap<String,Column> DETAIL_COLUMNS = columns("partId:i,supplierId:i,quantity:i,unitPrice:d,subtotal:d,remark:t");
    public RecordRepository(JdbcTemplate jdbc,ObjectMapper mapper) { this.jdbc=jdbc; this.mapper=mapper; }
    private static LinkedHashMap<String,Column> columns(String declaration) {
        var result=new LinkedHashMap<String,Column>();
        for (String entry:declaration.split(",")) {
            String[] pieces=entry.split(":");
            SqlType type=switch(pieces[1]) { case "i" -> SqlType.INTEGER; case "d" -> SqlType.DECIMAL; case "dt" -> SqlType.DATETIME; case "date" -> SqlType.DATE; default -> SqlType.TEXT; };
            result.put(pieces[0],new Column(pieces[0].replaceAll("([a-z])([A-Z])","$1_$2").toLowerCase(Locale.ROOT),type));
        }
        return result;
    }
    private static Table table(String name,String declaration) { return new Table(name,columns(declaration+",createTime:dt,updateTime:dt")); }
    private static Table table(String kind) { return Objects.requireNonNull(TABLES.get(kind),"Unknown record kind"); }
    public String encode(Object data) {
        try { return mapper.writeValueAsString(data); } catch (Exception e) { throw new IllegalStateException("JSON encoding failed",e); }
    }
    public Map<String,Object> decode(String text) {
        try { return mapper.readValue(text,TYPE); } catch (Exception e) { throw new IllegalStateException("Stored JSON is invalid",e); }
    }
    public void lockWrites() { jdbc.queryForObject("SELECT id FROM erp_write_guard WHERE id = 1 FOR UPDATE",Integer.class); }
    public List<Map<String,Object>> all(String kind) {
        Table target=table(kind);
        List<Map<String,Object>> rows=jdbc.query("SELECT * FROM "+target.name()+" ORDER BY id",(r,n) -> materialize(r,target.columns()));
        if (kind.equals("orders")) rows.forEach(row -> row.put("orderDetail",details(((Number)row.get("id")).longValue())));
        return rows;
    }
    public Map<String,Object> get(String kind,long id) {
        Table target=table(kind);
        Map<String,Object> row=jdbc.query("SELECT * FROM "+target.name()+" WHERE id = ?",(r,n) -> materialize(r,target.columns()),id)
            .stream().findFirst().orElseThrow(() -> new ApiException(404,kind+" record "+id+" not found"));
        if (kind.equals("orders")) row.put("orderDetail",details(id));
        return row;
    }
    private Map<String,Object> materialize(ResultSet result,LinkedHashMap<String,Column> mapping) throws SQLException {
        Map<String,Object> row=decode(result.getString("extra_json"));
        row.put("id",result.getLong("id")); populate(result,mapping,row); return row;
    }
    private void populate(ResultSet result,LinkedHashMap<String,Column> mapping,Map<String,Object> row) throws SQLException {
        for (var entry:mapping.entrySet()) {
            Column column=entry.getValue(); Object raw=result.getObject(column.name()); if (raw == null) continue;
            Object value=switch(column.type()) {
                case INTEGER -> result.getLong(column.name());
                case DECIMAL -> result.getBigDecimal(column.name());
                case DATETIME -> result.getTimestamp(column.name()).toLocalDateTime().toString();
                case DATE -> result.getDate(column.name()).toLocalDate().toString();
                case TEXT -> result.getString(column.name());
            };
            row.put(entry.getKey(),value);
        }
    }
    public Map<String,Object> insert(String kind,String ignoredBusinessKey,Map<String,Object> input) {
        Table target=table(kind); var data=new LinkedHashMap<>(input); data.remove("id");
        data.put("createTime",LocalDateTime.now().toString()); data.put("updateTime",data.get("createTime"));
        long id=nextId(kind,target.name());
        String columnNames=target.columns().values().stream().map(Column::name).collect(Collectors.joining(","));
        var args=new ArrayList<Object>(); args.add(id); args.addAll(values(target.columns(),data)); args.add(extraJson(data,target.columns()));
        jdbc.update("INSERT INTO "+target.name()+" (id,"+columnNames+",extra_json) VALUES ("+placeholders(args.size())+")",args.toArray());
        if (kind.equals("orders")) saveDetails(id,input);
        return get(kind,id);
    }
    public Map<String,Object> update(String kind,long id,String ignoredBusinessKey,Map<String,Object> input) {
        Table target=table(kind); var data=new LinkedHashMap<>(input); data.remove("id"); data.put("updateTime",LocalDateTime.now().toString());
        String assignments=target.columns().values().stream().map(column -> column.name()+" = ?").collect(Collectors.joining(","));
        var args=new ArrayList<>(values(target.columns(),data)); args.add(extraJson(data,target.columns())); args.add(id);
        jdbc.update("UPDATE "+target.name()+" SET "+assignments+",extra_json = ? WHERE id = ?",args.toArray());
        if (kind.equals("orders")) saveDetails(id,input);
        return get(kind,id);
    }
    public void delete(String kind,long id) { get(kind,id); jdbc.update("DELETE FROM "+table(kind).name()+" WHERE id = ?",id); }
    private long nextId(String kind,String tableName) {
        // Caller holds the transaction-scoped write guard. Sequence persists after deletion.
        List<Long> sequence=jdbc.query("SELECT next_id FROM erp_sequence WHERE kind = ?",(row,n) -> row.getLong(1),kind);
        if (sequence.isEmpty()) {
            long id=Objects.requireNonNull(jdbc.queryForObject("SELECT COALESCE(MAX(id),0)+1 FROM "+tableName,Long.class));
            jdbc.update("INSERT INTO erp_sequence(kind,next_id) VALUES (?,?)",kind,id+1); return id;
        }
        long id=sequence.get(0); jdbc.update("UPDATE erp_sequence SET next_id = ? WHERE kind = ?",id+1,kind); return id;
    }
    private List<Map<String,Object>> details(long orderId) {
        return jdbc.query("SELECT * FROM erp_order_detail WHERE order_id = ? ORDER BY line_number",(row,n) -> {
            Map<String,Object> data=decode(row.getString("extra_json")); data.put("id",row.getInt("line_number")); populate(row,DETAIL_COLUMNS,data); return data;
        },orderId);
    }
    @SuppressWarnings("unchecked")
    private void saveDetails(long orderId,Map<String,Object> data) {
        List<Map<String,Object>> supplied=(List<Map<String,Object>>)data.get("orderDetail");
        if (supplied.equals(details(orderId))) return; // Header-only updates leave detail rows untouched.
        jdbc.update("DELETE FROM erp_order_detail WHERE order_id = ?",orderId);
        String columnNames=DETAIL_COLUMNS.values().stream().map(Column::name).collect(Collectors.joining(","));
        for (int index=0; index<supplied.size(); index++) {
            Map<String,Object> line=supplied.get(index);
            var args=new ArrayList<Object>(); args.add(orderId); args.add(index+1); args.addAll(values(DETAIL_COLUMNS,line)); args.add(extraJson(line,DETAIL_COLUMNS));
            jdbc.update("INSERT INTO erp_order_detail(order_id,line_number,"+columnNames+",extra_json) VALUES ("+placeholders(args.size())+")",args.toArray());
        }
    }
    private List<Object> values(LinkedHashMap<String,Column> mapping,Map<String,Object> data) {
        var result=new ArrayList<Object>();
        for (var entry:mapping.entrySet()) {
            Object raw=data.get(entry.getKey());
            Object value=raw == null ? null : switch(entry.getValue().type()) {
                case TEXT -> raw.toString();
                case INTEGER -> new BigDecimal(raw.toString()).longValueExact();
                case DECIMAL -> new BigDecimal(raw.toString());
                case DATETIME -> Timestamp.valueOf(LocalDateTime.parse(raw.toString()));
                case DATE -> java.sql.Date.valueOf(LocalDate.parse(raw.toString()));
            };
            result.add(value);
        }
        return result;
    }
    private String extraJson(Map<String,Object> data,LinkedHashMap<String,Column> mapping) {
        Map<String,Object> extra=new LinkedHashMap<>(data); mapping.keySet().forEach(extra::remove);
        Set.of("id","orderDetail","partDetail","supplier","supplierName","orderId").forEach(extra::remove);
        return encode(extra);
    }
    private static String placeholders(int count) { return String.join(",",Collections.nCopies(count,"?")); }
    public Optional<Map<String,Object>> idempotency(String key) {
        return jdbc.query("SELECT payload_hash,response_json FROM erp_idempotency WHERE request_key = ?",(r,n) -> Map.<String,Object>of("hash",r.getString(1),"response",decode(r.getString(2))),key).stream().findFirst();
    }
    public void remember(String key,String hash,Object data) { jdbc.update("INSERT INTO erp_idempotency(request_key,payload_hash,response_json) VALUES (?,?,?)",key,hash,encode(Map.of("data",data))); }
    public void seedDemoUser() {
        if (all("users").isEmpty()) insert("users","demo-buyer",Map.of("username","demo-buyer","displayName","演示采购员","status",1));
    }
}
