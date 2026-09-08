package dev.asu.erp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @AutoConfigureMockMvc @ActiveProfiles("test")
class ErpIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired @Qualifier("requestMappingHandlerMapping") RequestMappingHandlerMapping mappings;
    @Autowired JdbcTemplate database;

    private JsonNode request(MockHttpServletRequestBuilder request, Object body, int status) throws Exception {
        if (body != null) request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsBytes(body));
        var response = mvc.perform(request).andExpect(status().is(status)).andExpect(jsonPath("$.code").value(status)).andExpect(jsonPath("$.timestamp").isNumber()).andReturn().getResponse();
        return json.readTree(response.getContentAsByteArray()).path("data");
    }
    private Map<String,Object> order(String number) {
        return Map.of("orderNumber",number,"orderDetail",List.of(Map.of("partId",1,"quantity",3,"unitPrice","0.10")));
    }

    @Test void partialUpdatePreservesLinesIdentifierAndCalculatedAmount() throws Exception {
        JsonNode created = request(post("/api/orders/create"),order("TEST-PARTIAL"),200);
        long id = created.path("id").asLong();
        JsonNode changed = request(put("/api/orders/update/"+id),Map.of("remark","header-only update"),200);
        assertThat(changed.path("orderNumber").asText()).isEqualTo("TEST-PARTIAL");
        assertThat(changed.path("orderTime")).isEqualTo(created.path("orderTime"));
        assertThat(changed.path("orderDetail").size()).isEqualTo(1);
        assertThat(changed.path("totalAmount").decimalValue()).isEqualByComparingTo(new BigDecimal("0.30"));
        assertThat(changed.path("orderDetail").get(0).path("quantity").asLong()).isEqualTo(3);
        request(put("/api/orders/update/"+id),Map.of("orderDetail",List.of()),400);
        assertThat(request(get("/api/orders/details/"+id),null,200).path("orderDetail").size()).isEqualTo(1);
        JsonNode replacement = request(put("/api/orders/update/"+id),Map.of("orderDetail",List.of(Map.of("partId",2,"quantity",2,"unitPrice","12.15"))),200);
        assertThat(replacement.path("totalAmount").decimalValue()).isEqualByComparingTo("24.30");
    }

    @Test void idempotencyReplaysAndRejectsDifferentPayloadIncludingConcurrentRetries() throws Exception {
        String key = "order-"+UUID.randomUUID(); Map<String,Object> body = order("TEST-IDEMPOTENCY");
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<JsonNode>> results = new ArrayList<>();
            for (int i=0;i<4;i++) results.add(pool.submit(() -> request(post("/api/orders/create").header("Idempotency-Key",key),body,200)));
            long firstId = results.get(0).get(15,TimeUnit.SECONDS).path("id").asLong();
            for (Future<JsonNode> result : results) assertThat(result.get(15,TimeUnit.SECONDS).path("id").asLong()).isEqualTo(firstId);
        } finally { pool.shutdownNow(); }
        request(post("/api/orders/create").header("Idempotency-Key",key),order("DIFFERENT-NUMBER"),409);
        JsonNode page = request(get("/api/orders/page").param("orderNumber","TEST-IDEMPOTENCY"),null,200);
        assertThat(page.path("total").asInt()).isEqualTo(1);
    }

    @Test void inventoryFiltersApplyBeforePaginationAndOverdrawRollsBack() throws Exception {
        JsonNode page = request(get("/api/inventory/page").param("partName","强化传动链条").param("current","1").param("size","1"),null,200);
        assertThat(page.path("total").asInt()).isEqualTo(1);
        assertThat(page.path("records").get(0).path("partId").asLong()).isEqualTo(3);
        JsonNode before = request(get("/api/inventory/check").param("partId","2"),null,200);
        request(post("/api/inventory/outbound"),Map.of("partId",2,"quantity",999999),409);
        JsonNode after = request(get("/api/inventory/check").param("partId","2"),null,200);
        assertThat(after.path("availableQuantity")).isEqualTo(before.path("availableQuantity"));
        String key = "stock-"+UUID.randomUUID();
        for (int i=0;i<2;i++) request(post("/api/inventory/inbound").header("Idempotency-Key",key),Map.of("partId",2,"quantity",5),200);
        JsonNode finalStock = request(get("/api/inventory/check").param("partId","2"),null,200);
        assertThat(finalStock.path("availableQuantity").asLong()).isEqualTo(before.path("availableQuantity").asLong()+5);
    }

    @Test void mcpReadContractsContainJoinedBusinessDetails() throws Exception {
        assertThat(request(get("/api/suppliers/search").param("name","示例"),null,200).size()).isEqualTo(3);
        assertThat(request(get("/api/parts/page").param("supplierId","1"),null,200).path("records").size()).isEqualTo(2);
        assertThat(request(get("/api/parts/search").param("name","刹车"),null,200).get(0).path("supplier").path("id").asLong()).isEqualTo(1);
        assertThat(request(get("/api/parts/supplier/3"),null,200).get(0).path("name").asText()).isEqualTo("强化传动链条");
        JsonNode details = request(get("/api/orders/search-details").param("partName","刹车").param("startDate","2026-01-01").param("endDate","2026-01-31"),null,200);
        assertThat(details.size()).isEqualTo(1);
        assertThat(details.get(0).path("partDetail").path("id").asLong()).isEqualTo(1);
        assertThat(details.get(0).path("supplier").path("name").asText()).isEqualTo("示例精工供应商");
        assertThat(request(get("/api/inventory/warning"),null,200).size()).isEqualTo(2);
    }

    @Test void moneyValidationRollbackAndStatusTransitions() throws Exception {
        Map<String,Object> invalid = new LinkedHashMap<>(order("TEST-BAD-MONEY")); invalid.put("totalAmount","9.99");
        request(post("/api/orders/create"),invalid,400);
        assertThat(request(get("/api/orders/page").param("orderNumber","TEST-BAD-MONEY"),null,200).path("total").asInt()).isZero();
        long id = request(post("/api/orders/create"),order("TEST-STATUS"),200).path("id").asLong();
        request(patch("/api/orders/update-status/"+id).param("status","4"),null,409);
        request(patch("/api/orders/update-status/"+id).param("status","2"),null,200);
        request(patch("/api/orders/update-status/"+id).param("status","3"),null,200);
        request(patch("/api/orders/update-status/"+id).param("status","4"),null,200);
        request(patch("/api/orders/update-status/"+id).param("status","1"),null,409);
        request(delete("/api/parts/delete/1"),null,409);
        request(get("/api/parts/page").param("size","0"),null,400);
    }

    @Test void customerLogisticsAndStatisticsFlows() throws Exception {
        long customer = request(post("/api/customers/create"),Map.of("name","合成客户测试","customerCode","TEST-CUSTOMER"),200).path("id").asLong();
        request(patch("/api/customers/update-discount/"+customer).param("discountRate","0.85"),null,200);
        request(patch("/api/customers/update-type/"+customer),Map.of("customerType",2),200);
        request(patch("/api/customers/update-discount/"+customer),Map.of("discountRate","1.2"),400);
        long order = request(post("/api/orders/create"),order("TEST-LOGISTICS"),200).path("id").asLong();
        long logistics = request(post("/api/logistics/create"),Map.of("orderId",order,"logisticsNumber","TEST-LOGISTICS-001"),200).path("id").asLong();
        request(patch("/api/logistics/update-shipping/"+logistics),Map.of("shippingDate","2026-09-08","trackingNumber","SYNTHETIC-TRACKING"),200);
        JsonNode received = request(patch("/api/logistics/update-receiving/"+logistics).param("receivingDate","2026-09-09"),null,200);
        assertThat(received.path("status").asInt()).isEqualTo(3);
        assertThat(request(get("/api/logistics/order/"+order),null,200).size()).isEqualTo(1);
        request(get("/api/statistics/dashboard"),null,200);
        request(get("/api/statistics/suppliers"),null,200);
        request(get("/api/statistics/parts"),null,200);
        request(get("/api/statistics/inventory"),null,200);
        assertThat(request(get("/api/statistics/monthly-trend").param("year","2026"),null,200).size()).isEqualTo(12);
        request(delete("/api/customers/delete/"+customer),null,200);
        request(get("/api/customers/get/"+customer),null,404);
    }

    @Test void all54DeclaredCompatibilityRoutesAreActuallyRegistered() throws Exception {
        JsonNode expected = json.readTree(Objects.requireNonNull(getClass().getResourceAsStream("/endpoint-manifest.json")));
        Set<String> registered = new HashSet<>();
        mappings.getHandlerMethods().forEach((mapping,handler) -> mapping.getPatternValues().forEach(path -> mapping.getMethodsCondition().getMethods().forEach(method -> registered.add(method.name()+" "+path))));
        assertThat(expected.size()).isEqualTo(54);
        for (JsonNode route : expected) assertThat(registered).contains(route.asText());
    }

    @Test void relationalColumnsForeignKeysAndMoneyConstraintsAreEnforced() {
        assertThat(database.queryForObject("SELECT total_amount FROM erp_purchase_order WHERE id=1",BigDecimal.class)).isEqualByComparingTo("834.50");
        assertThat(database.queryForObject("SELECT COUNT(*) FROM erp_order_detail WHERE order_id=1",Integer.class)).isEqualTo(2);
        assertThat(database.queryForObject("SELECT extra_json FROM erp_purchase_order WHERE id=1",String.class)).doesNotContain("totalAmount","orderDetail");
        assertThat(database.queryForObject("SELECT created_by FROM erp_purchase_order WHERE id=1",Long.class)).isEqualTo(1);
        assertThatThrownBy(() -> database.update("UPDATE erp_part SET supplier_id=99999 WHERE id=1")).isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        assertThatThrownBy(() -> database.update("UPDATE erp_inventory SET quantity=-1 WHERE id=1")).isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        assertThatThrownBy(() -> database.update("UPDATE erp_order_detail SET subtotal=1.23 WHERE order_id=1 AND line_number=1")).isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    }

    @Test void remainingCrudEndpointsPersistBusinessChanges() throws Exception {
        long supplier=request(post("/api/suppliers/create"),Map.of("name","独立供应商测试","supplierCode","TEST-CRUD-SUP"),200).path("id").asLong();
        request(put("/api/suppliers/update/"+supplier),Map.of("address","合成地址"),200);
        request(patch("/api/suppliers/update-status/"+supplier),Map.of("status",0),200);
        request(patch("/api/suppliers/update-credit-rating/"+supplier).param("creditRating","AA"),null,200);
        assertThat(request(get("/api/suppliers/get/"+supplier),null,200).path("address").asText()).isEqualTo("合成地址");
        request(get("/api/suppliers/page").param("name","独立"),null,200);
        long part=request(post("/api/parts/create"),Map.of("name","独立零件测试","partCode","TEST-CRUD-PART","category","外观件","supplierId",supplier,"price","3.15"),200).path("id").asLong();
        request(put("/api/parts/update/"+part),Map.of("specification","合成规格"),200);
        request(patch("/api/parts/update-price/"+part).param("price","3.25"),null,200);
        assertThat(request(get("/api/parts/get/"+part),null,200).path("price").decimalValue()).isEqualByComparingTo("3.25");
        request(delete("/api/parts/delete/"+part),null,200);
        request(delete("/api/suppliers/delete/"+supplier),null,200);
        long order=request(post("/api/orders/create"),order("TEST-DELETE-ORDER"),200).path("id").asLong();
        request(get("/api/orders/get/"+order),null,200);
        request(get("/api/orders/statistics"),null,200);
        long logistic=request(post("/api/logistics/create"),Map.of("orderId",order,"logisticsNumber","TEST-DELETE-LOGISTIC"),200).path("id").asLong();
        request(put("/api/logistics/update/"+logistic),Map.of("remark","合成物流备注"),200);
        request(patch("/api/logistics/update-status/"+logistic).param("status","2"),null,200);
        request(get("/api/logistics/get/"+logistic),null,200);
        request(get("/api/logistics/page").param("orderId",String.valueOf(order)),null,200);
        request(delete("/api/logistics/delete/"+logistic),null,200);
        request(delete("/api/orders/delete/"+order),null,200);
        assertThat(database.queryForObject("SELECT COUNT(*) FROM erp_order_detail WHERE order_id=?",Integer.class,order)).isZero();
        long customer=request(post("/api/customers/create"),Map.of("name","独立客户测试","customerCode","TEST-CRUD-CUSTOMER"),200).path("id").asLong();
        request(put("/api/customers/update/"+customer),Map.of("name","独立客户改名"),200);
        assertThat(request(get("/api/customers/search").param("name","独立客户改名"),null,200).size()).isEqualTo(1);
        request(get("/api/customers/page").param("name","独立"),null,200);
        request(delete("/api/customers/delete/"+customer),null,200);
        request(get("/api/inventory/get/2"),null,200);
        request(patch("/api/inventory/update-safety-stock/2").param("safetyStock","15"),null,200);
    }

    @Test void competingOutboundRequestsCannotOversell() throws Exception {
        long available=request(get("/api/inventory/check").param("partId","2"),null,200).path("availableQuantity").asLong();
        long requested=available-1;
        ExecutorService pool=Executors.newFixedThreadPool(2);
        CountDownLatch gate=new CountDownLatch(1);
        try {
            List<Future<Integer>> calls=new ArrayList<>();
            for (int i=0;i<2;i++) calls.add(pool.submit(() -> {
                gate.await();
                return mvc.perform(post("/api/inventory/outbound").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsBytes(Map.of("partId",2,"quantity",requested)))).andReturn().getResponse().getStatus();
            }));
            gate.countDown();
            List<Integer> statuses=List.of(calls.get(0).get(15,TimeUnit.SECONDS),calls.get(1).get(15,TimeUnit.SECONDS));
            assertThat(statuses).containsExactlyInAnyOrder(200,409);
            assertThat(request(get("/api/inventory/check").param("partId","2"),null,200).path("availableQuantity").asLong()).isEqualTo(1);
        } finally {
            pool.shutdownNow();
            long remaining=request(get("/api/inventory/check").param("partId","2"),null,200).path("availableQuantity").asLong();
            if (remaining < available) request(post("/api/inventory/inbound"),Map.of("partId",2,"quantity",available-remaining),200);
        }
    }

    @Test void headerUpdateRetainsHistoricalSupplierAfterCatalogChange() throws Exception {
        long id=request(post("/api/orders/create"),Map.of("orderNumber","TEST-SUPPLIER-SNAPSHOT","orderDetail",List.of(Map.of("partId",2,"quantity",2,"unitPrice","4.00"))),200).path("id").asLong();
        try {
            request(put("/api/parts/update/2"),Map.of("supplierId",3),200);
            JsonNode changed=request(put("/api/orders/update/"+id),Map.of("remark","preserve historical supplier"),200);
            assertThat(changed.path("orderDetail").get(0).path("supplier").path("id").asLong()).isEqualTo(1);
            assertThat(database.queryForObject("SELECT supplier_id FROM erp_order_detail WHERE order_id=? AND line_number=1",Long.class,id)).isEqualTo(1);
        } finally {
            request(put("/api/parts/update/2"),Map.of("supplierId",1),200);
            request(delete("/api/orders/delete/"+id),null,200);
        }
    }
}
