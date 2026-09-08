package dev.asu.erp;

import java.util.Map;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** All examples are synthetic and have no connection to any real enterprise. */
@Component
public class SeedData implements ApplicationRunner {
    private final ErpService service;
    private final RecordRepository records;
    private final boolean enabled;
    public SeedData(ErpService service, RecordRepository records, @Value("${erp.seed-enabled:true}") boolean enabled) {
        this.service=service; this.records=records; this.enabled=enabled;
    }
    @Override @Transactional
    public void run(ApplicationArguments arguments) {
        if (!enabled) return;
        records.lockWrites();
        if (!records.all("suppliers").isEmpty() || !records.all("parts").isEmpty()) return;
        records.seedDemoUser();
        service.write("suppliers","create",null,Map.of("name","示例精工供应商","supplierCode","DEMO-SUP-001","contactPerson","演示联系人甲","email","supplier-a@example.invalid","address","合成数据演示园区 A 栋","creditRating","A"),null);
        service.write("suppliers","create",null,Map.of("name","示例动力供应商","supplierCode","DEMO-SUP-002","contactPerson","演示联系人乙","email","supplier-b@example.invalid","creditRating","B"),null);
        service.write("suppliers","create",null,Map.of("name","示例传动供应商","supplierCode","DEMO-SUP-003","contactPerson","演示联系人丙","email","supplier-c@example.invalid","creditRating","AA"),null);
        service.write("parts","create",null,Map.of("name","陶瓷刹车片","partCode","DEMO-PART-001","category","制动类","supplierId",1,"price","38.50","specification","演示型号 BP-A"),null);
        service.write("parts","create",null,Map.of("name","铝合金制动盘","partCode","DEMO-PART-002","category","制动类","supplierId",1,"price","126.80","specification","演示型号 BD-B"),null);
        service.write("parts","create",null,Map.of("name","强化传动链条","partCode","DEMO-PART-003","category","传动类","supplierId",3,"price","89.90","specification","演示型号 CH-C"),null);
        service.write("inventory","inbound",null,Map.of("partId",1,"quantity",8,"safetyStock",20),null);
        service.write("inventory","inbound",null,Map.of("partId",2,"quantity",36,"safetyStock",15),null);
        service.write("inventory","inbound",null,Map.of("partId",3,"quantity",4,"safetyStock",10),null);
        service.write("customers","create",null,Map.of("name","示例维修门店","customerCode","DEMO-CUSTOMER-001","customerType",1,"discountRate","0.95"),null);
        service.write("orders","create",null,Map.of("orderNumber","DEMO-PO-001","orderTime","2026-01-15T10:00:00","createdBy",1,"remark","完全合成的历史演示订单","orderDetail",List.of(Map.of("partId",1,"quantity",10,"unitPrice","38.50"),Map.of("partId",3,"quantity",5,"unitPrice","89.90"))),null);
        service.write("logistics","create",null,Map.of("orderId",1,"logisticsNumber","DEMO-LG-001","logisticsCompany","示例物流","status",1,"remark","仅用于演示，不触发真实物流"),null);
    }
}
