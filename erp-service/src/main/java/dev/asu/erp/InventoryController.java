package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController extends ErpControllerSupport {
    public InventoryController(ErpService service) { super(service, "inventory"); }
    @GetMapping("/get/{id}")
    public ApiResponse get(@PathVariable long id, @RequestParam Map<String,String> query) { return read("get",id,query); }
    @GetMapping("/page")
    public ApiResponse page(@RequestParam Map<String,String> query) { return read("page",null,query); }
    @GetMapping("/warning")
    public ApiResponse warning(@RequestParam Map<String,String> query) { return read("warning",null,query); }
    @GetMapping("/check")
    public ApiResponse check(@RequestParam Map<String,String> query) { return read("check",null,query); }
    @PatchMapping("/update-safety-stock/{id}")
    public ApiResponse updateSafetyStock(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-safety-stock",id,merged(query,body),key); }
    @PostMapping("/inbound")
    public ApiResponse inbound(@RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("inbound",null,merged(query,body),key); }
    @PostMapping("/outbound")
    public ApiResponse outbound(@RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("outbound",null,merged(query,body),key); }
}

