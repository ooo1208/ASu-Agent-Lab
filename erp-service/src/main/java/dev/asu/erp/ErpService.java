package dev.asu.erp;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Isolation;

/** Relational teaching ERP. Database transactions, not JVM locks, serialize mutations. */
@Service
public class ErpService {
    private final RecordRepository records;
    private static final Set<String> KINDS = Set.of("suppliers", "parts", "orders", "inventory", "customers", "logistics");
    private static final Map<String,String> KEYS = Map.of("suppliers","supplierCode", "parts","partCode", "orders","orderNumber", "inventory","partId", "customers","customerCode", "logistics","logisticsNumber");
    public ErpService(RecordRepository records) { this.records = records; }

    @Transactional
    public Object write(String kind, String action, Long id, Map<String,Object> input, String idempotencyKey) {
        requireKind(kind);
        records.lockWrites();
        Map<String,Object> body = new LinkedHashMap<>(input);
        String hash = fingerprint(Map.of("kind", kind, "action", action, "id", id == null ? 0 : id, "body", body));
        if (idempotencyKey != null) {
            if (idempotencyKey.isBlank() || idempotencyKey.length() > 128) throw ApiException.bad("Idempotency-Key must contain 1..128 characters");
            var previous = records.idempotency(idempotencyKey);
            if (previous.isPresent()) {
                if (!hash.equals(previous.get().get("hash"))) throw ApiException.conflict("Idempotency-Key was already used for a different request");
                return ((Map<?,?>) previous.get().get("response")).get("data");
            }
        }
        Object result = switch (action) {
            case "create" -> create(kind, body);
            case "update" -> update(kind, requiredId(id), body);
            case "delete" -> delete(kind, requiredId(id));
            case "inbound", "outbound" -> moveStock(action, body);
            default -> patch(kind, action, requiredId(id), body);
        };
        if (idempotencyKey != null) records.remember(idempotencyKey, hash, result);
        return result;
    }

    @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
    public Object read(String kind, String action, Long id, Map<String,String> query) {
        if (kind.equals("statistics")) return statistics(action, query);
        requireKind(kind);
        if (action.equals("get") || action.equals("details")) return enrich(kind, records.get(kind, requiredId(id)));
        if (action.equals("search-details")) return orderDetails(query);
        if (action.equals("statistics")) return orderStatistics(filter("orders", query));
        if (action.equals("check")) {
            long partId = positiveLong(query.get("partId"), "partId");
            records.get("parts", partId);
            long quantity = positiveLong(query.getOrDefault("quantity", "1"), "quantity");
            long available = records.all("inventory").stream().filter(row -> number(row.get("partId")) == partId).mapToLong(row -> number(row.get("quantity"))).sum();
            return Map.of("partId",partId,"requiredQuantity",quantity,"availableQuantity",available,"sufficient",available >= quantity);
        }
        var criteria = new LinkedHashMap<>(query);
        if (action.equals("supplier")) criteria.put("supplierId", String.valueOf(requiredId(id)));
        if (action.equals("order")) criteria.put("orderId", String.valueOf(requiredId(id)));
        if (action.equals("warning")) criteria.put("warningOnly", "true");
        List<Map<String,Object>> found = filter(kind, criteria);
        if (action.equals("page")) return page(found, query);
        return found;
    }

    private Map<String,Object> create(String kind, Map<String,Object> data) {
        data.remove("id"); data.remove("createTime"); data.remove("updateTime");
        switch (kind) {
            case "suppliers" -> { data.putIfAbsent("status",1); data.putIfAbsent("creditRating","A"); }
            case "parts" -> { data.putIfAbsent("status",1); data.putIfAbsent("unit","件"); }
            case "orders" -> {
                data.putIfAbsent("status",1);
                if (nonnegativeLong(data.get("status"),"status") != 1) throw ApiException.bad("New orders must start at status 1 (pending approval)");
                data.putIfAbsent("orderNumber", "PO-" + UUID.randomUUID());
                data.putIfAbsent("orderTime",LocalDateTime.now().toString());
            }
            case "customers" -> { data.putIfAbsent("customerType",1); data.putIfAbsent("discountRate",new BigDecimal("1.00")); }
            case "logistics" -> { data.putIfAbsent("status",1); data.putIfAbsent("logisticsNumber", "LG-" + UUID.randomUUID()); }
            default -> throw ApiException.bad("Use inbound to create inventory");
        }
        String key = KEYS.get(kind);
        if (!kind.equals("inventory")) data.putIfAbsent(key, kind.substring(0,3).toUpperCase(Locale.ROOT) + "-" + UUID.randomUUID());
        validate(kind, data, null);
        return enrich(kind, records.insert(kind, String.valueOf(data.get(key)), data));
    }

    private Map<String,Object> update(String kind, long id, Map<String,Object> changes) {
        Map<String,Object> previous = records.get(kind,id);
        Map<String,Object> merged = new LinkedHashMap<>(previous);
        for (var entry : changes.entrySet()) {
            if (Set.of("id","createTime","updateTime").contains(entry.getKey())) continue;
            if (entry.getValue() == null) throw ApiException.bad(entry.getKey() + " cannot be null; omit it to preserve the existing value");
            merged.put(entry.getKey(), entry.getValue());
        }
        // Absence of orderDetail deliberately preserves the existing lines and amount.
        if (kind.equals("orders") && changes.containsKey("orderDetail") && !changes.containsKey("totalAmount")) merged.remove("totalAmount");
        validate(kind, merged, previous);
        return enrich(kind, records.update(kind,id,String.valueOf(merged.get(KEYS.get(kind))),merged));
    }

    private Object patch(String kind, String action, long id, Map<String,Object> body) {
        List<String> fields = switch (action) {
            case "update-status" -> List.of("status");
            case "update-credit-rating" -> List.of("creditRating");
            case "update-price" -> List.of("price");
            case "update-safety-stock" -> List.of("safetyStock");
            case "update-type" -> List.of("customerType");
            case "update-discount" -> List.of("discountRate");
            case "update-shipping" -> List.of("shippingDate", "trackingNumber", "logisticsCompany");
            case "update-receiving" -> List.of("receivingDate", "receiver", "remark");
            default -> throw new ApiException(404,"Unknown action");
        };
        var patch = new LinkedHashMap<String,Object>();
        for (String field : fields) if (body.containsKey(field)) patch.put(field,body.get(field));
        if (patch.isEmpty()) throw ApiException.bad("Expected one of: " + String.join(", ",fields));
        if (action.equals("update-shipping")) patch.put("status",2);
        if (action.equals("update-receiving")) patch.put("status",3);
        return update(kind,id,patch);
    }

    private Object delete(String kind, long id) {
        records.get(kind,id);
        boolean referenced = switch (kind) {
            case "suppliers" -> records.all("parts").stream().anyMatch(x -> number(x.get("supplierId")) == id);
            case "parts" -> records.all("inventory").stream().anyMatch(x -> number(x.get("partId")) == id)
                    || records.all("orders").stream().flatMap(x -> lines(x).stream()).anyMatch(x -> number(x.get("partId")) == id);
            case "orders" -> records.all("logistics").stream().anyMatch(x -> number(x.get("orderId")) == id);
            default -> false;
        };
        if (referenced) throw ApiException.conflict("Record is referenced by another business record");
        if (kind.equals("orders") && !Set.of(1L,5L).contains(number(records.get(kind,id).get("status")))) throw ApiException.conflict("Only pending or cancelled orders can be deleted");
        records.delete(kind,id); return Map.of("id",id,"deleted",true);
    }

    private Map<String,Object> moveStock(String action, Map<String,Object> body) {
        long partId = positiveLong(body.get("partId"),"partId"); records.get("parts",partId);
        long delta = positiveLong(body.get("quantity"),"quantity");
        var existing = records.all("inventory").stream().filter(x -> number(x.get("partId")) == partId).findFirst();
        if (existing.isEmpty() && action.equals("outbound")) throw ApiException.conflict("No inventory for this part");
        var data = existing.map(LinkedHashMap::new).orElseGet(LinkedHashMap::new);
        long current = number(data.getOrDefault("quantity",0));
        if (action.equals("outbound") && current < delta) throw ApiException.conflict("Insufficient inventory; stock was not changed");
        try { data.put("quantity", action.equals("inbound") ? Math.addExact(current,delta) : current-delta); }
        catch (ArithmeticException e) { throw ApiException.bad("Quantity is too large"); }
        data.put("partId",partId);
        data.putIfAbsent("safetyStock",nonnegativeLong(body.getOrDefault("safetyStock",0),"safetyStock"));
        data.putIfAbsent("warehouseLocation",body.getOrDefault("warehouseLocation","DEMO-WH-A"));
        data.put(action.equals("inbound") ? "lastInboundTime" : "lastOutboundTime",LocalDateTime.now().toString());
        Map<String,Object> saved = existing.isPresent()
                ? records.update("inventory",number(data.get("id")),String.valueOf(partId),data)
                : records.insert("inventory",String.valueOf(partId),data);
        return enrich("inventory",saved);
    }

    private void validate(String kind, Map<String,Object> data, Map<String,Object> previous) {
        requiredText(data,KEYS.get(kind));
        switch (kind) {
            case "suppliers" -> {
                requiredText(data,"name"); range(data,"status",0,1);
                if (!Set.of("AAA","AA","A","B","C","D").contains(text(data.get("creditRating")))) throw ApiException.bad("Unsupported creditRating");
            }
            case "parts" -> {
                requiredText(data,"name"); requiredText(data,"category");
                records.get("suppliers",positiveLong(data.get("supplierId"),"supplierId"));
                data.put("price", money(data.get("price"),"price")); range(data,"status",0,1);
            }
            case "orders" -> {
                range(data,"status",1,5);
                if (previous != null) validateOrderTransition(number(previous.get("status")),number(data.get("status")));
                requireDateTime(data,"orderTime"); optionalDate(data,"expectedDeliveryDate"); optionalDate(data,"actualDeliveryDate");
                if (data.containsKey("createdBy")) records.get("users",positiveLong(data.get("createdBy"),"createdBy"));
                List<Map<String,Object>> details = lines(data);
                if (details.isEmpty()) throw ApiException.bad("orderDetail must contain at least one line");
                boolean unchangedLines = previous != null && Objects.equals(data.get("orderDetail"), previous.get("orderDetail"));
                var normalized = new ArrayList<Map<String,Object>>(); BigDecimal total = BigDecimal.ZERO;
                for (int i = 0; i < details.size(); i++) {
                    var item = new LinkedHashMap<>(details.get(i));
                    long partId = positiveLong(item.get("partId"),"orderDetail.partId");
                    Map<String,Object> part = records.get("parts",partId);
                    long quantity = positiveLong(item.get("quantity"),"orderDetail.quantity");
                    BigDecimal unitPrice = money(item.get("unitPrice"),"orderDetail.unitPrice");
                    BigDecimal subtotal = unitPrice.multiply(BigDecimal.valueOf(quantity)).setScale(2,RoundingMode.UNNECESSARY);
                    money(subtotal,"subtotal");
                    if (item.containsKey("subtotal") && money(item.get("subtotal"),"subtotal").compareTo(subtotal) != 0) throw ApiException.bad("Line subtotal does not equal quantity × unitPrice");
                    item.put("id",i+1); item.put("partId",partId); item.put("quantity",quantity); item.put("unitPrice",unitPrice); item.put("subtotal",subtotal);
                    if (!unchangedLines) item.put("supplierId",part.get("supplierId"));
                    item.remove("partDetail"); item.remove("supplier"); normalized.add(item); total = total.add(subtotal);
                }
                if (data.containsKey("totalAmount") && money(data.get("totalAmount"),"totalAmount").compareTo(total) != 0) throw ApiException.bad("totalAmount does not match order lines");
                data.put("orderDetail",normalized); data.put("totalAmount",money(total,"totalAmount"));
            }
            case "inventory" -> { data.put("safetyStock",nonnegativeLong(data.get("safetyStock"),"safetyStock")); }
            case "customers" -> {
                requiredText(data,"name"); range(data,"customerType",1,3);
                BigDecimal rate = decimal(data.get("discountRate"),"discountRate");
                if (rate.signum() < 0 || rate.compareTo(BigDecimal.ONE) > 0) throw ApiException.bad("discountRate must be between 0 and 1");
                if (rate.stripTrailingZeros().scale() > 4) throw ApiException.bad("discountRate supports at most four decimal places");
                data.put("discountRate",rate);
            }
            case "logistics" -> {
                records.get("orders",positiveLong(data.get("orderId"),"orderId")); range(data,"status",1,4);
                optionalDate(data,"shippingDate"); optionalDate(data,"receivingDate");
            }
        }
    }

    private List<Map<String,Object>> filter(String kind, Map<String,String> query) {
        if (query.containsKey("startDate")) parseDate(query.get("startDate"),"startDate");
        if (query.containsKey("endDate")) parseDate(query.get("endDate"),"endDate");
        if (query.containsKey("startDate") && query.containsKey("endDate") && parseDate(query.get("startDate"),"startDate").isAfter(parseDate(query.get("endDate"),"endDate"))) throw ApiException.bad("startDate must not be after endDate");
        // Enrichment and all predicates precede pagination, including joined partName filters.
        return records.all(kind).stream().map(row -> enrich(kind,row)).filter(row -> {
            for (var entry : query.entrySet()) {
                String field = entry.getKey(), value = entry.getValue();
                if (value == null || value.isBlank() || Set.of("current","size","startDate","endDate").contains(field)) continue;
                switch (field) {
                    case "name", "orderNumber", "warehouseLocation", "logisticsNumber", "trackingNumber" -> { if (!contains(row.get(field),value)) return false; }
                    case "partName" -> { if (!contains(row.get("partName"),value)) return false; }
                    case "category", "status", "supplierId", "partId", "orderId", "customerType", "creditRating" -> { if (!text(row.get(field)).equals(value)) return false; }
                    case "warningOnly", "isWarning" -> { if (Boolean.parseBoolean(value) && number(row.get("quantity")) >= number(row.get("safetyStock"))) return false; }
                    case "minQuantity" -> { if (number(row.get("quantity")) < nonnegativeLong(value,field)) return false; }
                    case "maxQuantity" -> { if (number(row.get("quantity")) > nonnegativeLong(value,field)) return false; }
                    default -> throw ApiException.bad("Unsupported filter: " + field);
                }
            }
            if (kind.equals("orders")) {
                LocalDate day = LocalDateTime.parse(text(row.get("orderTime"))).toLocalDate();
                if (query.containsKey("startDate") && day.isBefore(parseDate(query.get("startDate"),"startDate"))) return false;
                if (query.containsKey("endDate") && day.isAfter(parseDate(query.get("endDate"),"endDate"))) return false;
            }
            return true;
        }).toList();
    }

    private Map<String,Object> enrich(String kind, Map<String,Object> input) {
        var data = new LinkedHashMap<>(input);
        if (kind.equals("parts")) {
            Map<String,Object> supplier = records.get("suppliers",number(data.get("supplierId")));
            data.put("supplier",supplier); data.put("supplierName",supplier.get("name"));
        }
        if (kind.equals("inventory")) {
            Map<String,Object> part = enrich("parts",records.get("parts",number(data.get("partId"))));
            data.put("partDetail",part); data.put("partName",part.get("name")); data.put("category",part.get("category"));
            data.put("isWarning",number(data.get("quantity")) < number(data.get("safetyStock")));
        }
        if (kind.equals("orders")) {
            var enriched = new ArrayList<Map<String,Object>>();
            for (var line : lines(data)) {
                var detail = new LinkedHashMap<>(line);
                Map<String,Object> part = enrich("parts",records.get("parts",number(line.get("partId"))));
                detail.put("partDetail",part); detail.put("supplier",records.get("suppliers",number(line.get("supplierId")))); detail.put("orderId",data.get("id")); enriched.add(detail);
            }
            data.put("orderDetail",enriched);
        }
        return data;
    }

    private List<Map<String,Object>> orderDetails(Map<String,String> query) {
        var orderQuery = new LinkedHashMap<>(query); String name = orderQuery.remove("partName");
        var found = new ArrayList<Map<String,Object>>();
        for (Map<String,Object> order : filter("orders",orderQuery)) for (Map<String,Object> line : lines(order)) {
            Map<?,?> part = (Map<?,?>) line.get("partDetail");
            if (name != null && !contains(part.get("name"),name)) continue;
            var row = new LinkedHashMap<>(line);
            row.put("orderNumber",order.get("orderNumber")); row.put("orderTime",order.get("orderTime")); row.put("status",order.get("status")); found.add(row);
        }
        return found;
    }

    private Object page(List<Map<String,Object>> found, Map<String,String> query) {
        long current = positiveLong(query.getOrDefault("current","1"),"current"), size = positiveLong(query.getOrDefault("size","10"),"size");
        if (size > 200) throw ApiException.bad("size must be at most 200");
        long offset;
        try { offset = Math.multiplyExact(current-1,size); } catch (ArithmeticException e) { throw ApiException.bad("Page offset is too large"); }
        List<Map<String,Object>> rows = offset >= found.size() ? List.of() : found.subList((int)offset,(int)Math.min(offset+size,found.size()));
        return Map.of("records",rows,"total",found.size(),"current",current,"size",size,"pages",(found.size()+size-1)/size);
    }

    private Object statistics(String action, Map<String,String> query) {
        List<Map<String,Object>> orders = records.all("orders");
        return switch (action) {
            case "dashboard" -> Map.of("supplierCount",records.all("suppliers").size(),"partCount",records.all("parts").size(),"customerCount",records.all("customers").size(),"orderCount",orders.size(),"inventoryWarningCount",filter("inventory",Map.of("warningOnly","true")).size(),"totalPurchaseAmount",total(orders));
            case "suppliers" -> group(records.all("suppliers"),"creditRating");
            case "parts" -> group(records.all("parts"),"category");
            case "inventory" -> Map.of("totalQuantity",records.all("inventory").stream().mapToLong(x -> number(x.get("quantity"))).sum(),"warningCount",filter("inventory",Map.of("warningOnly","true")).size());
            case "monthly-trend" -> {
                long year = positiveLong(query.getOrDefault("year",String.valueOf(LocalDate.now().getYear())),"year");
                if (year > 9999) throw ApiException.bad("year must be at most 9999");
                var result = new ArrayList<Map<String,Object>>();
                for (int month=1; month<=12; month++) {
                    String prefix = YearMonth.of((int)year,month).toString();
                    var rows = orders.stream().filter(x -> text(x.get("orderTime")).startsWith(prefix)).toList();
                    result.add(Map.of("month",prefix,"orderCount",rows.size(),"totalAmount",total(rows)));
                }
                yield result;
            }
            default -> throw new ApiException(404,"Unknown statistics endpoint");
        };
    }
    private Object orderStatistics(List<Map<String,Object>> rows) { return Map.of("totalOrders",rows.size(),"totalAmount",total(rows),"byStatus",group(rows,"status")); }
    private List<Map<String,Object>> group(List<Map<String,Object>> rows,String field) {
        return rows.stream().collect(Collectors.groupingBy(x -> text(x.get(field)),TreeMap::new,Collectors.counting())).entrySet().stream().map(x -> Map.<String,Object>of(field,x.getKey(),"count",x.getValue())).toList();
    }
    private BigDecimal total(List<Map<String,Object>> rows) { return rows.stream().filter(x -> number(x.get("status")) != 5).map(x -> decimal(x.get("totalAmount"),"totalAmount")).reduce(BigDecimal.ZERO,BigDecimal::add).setScale(2); }

    private static void validateOrderTransition(long from,long to) {
        if (from == to) return;
        Map<Long,Set<Long>> allowed = Map.of(1L,Set.of(2L,5L),2L,Set.of(3L,5L),3L,Set.of(4L,5L),4L,Set.of(),5L,Set.of());
        if (!allowed.getOrDefault(from,Set.of()).contains(to)) throw ApiException.conflict("Invalid order status transition " + from + " -> " + to);
    }
    private static void requireKind(String kind) { if (!KINDS.contains(kind)) throw new ApiException(404,"Unknown business module"); }
    private static long requiredId(Long id) { if (id == null || id <= 0) throw ApiException.bad("Positive id required"); return id; }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
    private static boolean contains(Object actual,String expected) { return text(actual).toLowerCase(Locale.ROOT).contains(expected.toLowerCase(Locale.ROOT)); }
    private static void requiredText(Map<String,Object> data,String field) { if (text(data.get(field)).isBlank()) throw ApiException.bad(field + " is required"); }
    private static BigDecimal decimal(Object value,String field) {
        try { if (value == null) throw new NumberFormatException(); return new BigDecimal(value.toString()); }
        catch (NumberFormatException e) { throw ApiException.bad(field + " must be a decimal number"); }
    }
    private static BigDecimal money(Object value,String field) {
        BigDecimal amount = decimal(value,field);
        if (amount.signum() < 0) throw ApiException.bad(field + " must be nonnegative");
        try {
            BigDecimal scaled=amount.setScale(2,RoundingMode.UNNECESSARY);
            if (scaled.precision() > 18) throw ApiException.bad(field + " exceeds DECIMAL(18,2)");
            return scaled;
        } catch (ArithmeticException e) { throw ApiException.bad(field + " supports at most two decimal places"); }
    }
    private static long number(Object value) { return value == null ? 0 : new BigDecimal(value.toString()).longValueExact(); }
    private static long nonnegativeLong(Object value,String field) {
        try { long number = decimal(value,field).longValueExact(); if (number < 0) throw new ArithmeticException(); return number; }
        catch (ArithmeticException e) { throw ApiException.bad(field + " must be a nonnegative integer"); }
    }
    private static long positiveLong(Object value,String field) { long number = nonnegativeLong(value,field); if (number == 0) throw ApiException.bad(field + " must be positive"); return number; }
    private static void range(Map<String,Object> data,String field,int min,int max) { long value = nonnegativeLong(data.get(field),field); if (value < min || value > max) throw ApiException.bad(field + " must be between " + min + " and " + max); data.put(field,value); }
    private static LocalDate parseDate(String value,String field) { try { return LocalDate.parse(value); } catch (Exception e) { throw ApiException.bad(field + " must use yyyy-MM-dd"); } }
    private static void optionalDate(Map<String,Object> data,String field) { if (data.containsKey(field)) parseDate(text(data.get(field)),field); }
    private static void requireDateTime(Map<String,Object> data,String field) { try { LocalDateTime.parse(text(data.get(field))); } catch (Exception e) { throw ApiException.bad(field + " must be an ISO local date-time"); } }
    @SuppressWarnings("unchecked")
    private static List<Map<String,Object>> lines(Map<String,Object> data) {
        Object value = data.get("orderDetail");
        if (!(value instanceof List<?> list) || list.stream().anyMatch(x -> !(x instanceof Map<?,?>))) throw ApiException.bad("orderDetail must be an array of objects");
        return (List<Map<String,Object>>)value;
    }
    private String fingerprint(Object value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(records.encode(canonical(value)).getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException("Cannot fingerprint request",e); }
    }
    private Object canonical(Object value) {
        if (value instanceof Map<?,?> map) { var sorted = new TreeMap<String,Object>(); map.forEach((key,item) -> sorted.put(key.toString(),canonical(item))); return sorted; }
        if (value instanceof List<?> list) return list.stream().map(this::canonical).toList();
        if (value instanceof Number number) return new BigDecimal(number.toString()).stripTrailingZeros();
        return value;
    }
}
