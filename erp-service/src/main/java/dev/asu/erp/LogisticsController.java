package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/logistics")
public class LogisticsController extends ErpControllerSupport {
    public LogisticsController(ErpService service) { super(service, "logistics"); }
    @PostMapping("/create")
    public ApiResponse create(@RequestHeader(name="Idempotency-Key",required=false) String key, @RequestBody Map<String,Object> body) { return write("create",null,body,key); }
    @PutMapping("/update/{id}")
    public ApiResponse update(@PathVariable long id, @RequestHeader(name="Idempotency-Key",required=false) String key, @RequestBody Map<String,Object> body) { return write("update",id,body,key); }
    @DeleteMapping("/delete/{id}")
    public ApiResponse delete(@PathVariable long id, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("delete",id,Map.of(),key); }
    @GetMapping("/get/{id}")
    public ApiResponse get(@PathVariable long id, @RequestParam Map<String,String> query) { return read("get",id,query); }
    @GetMapping("/page")
    public ApiResponse page(@RequestParam Map<String,String> query) { return read("page",null,query); }
    @GetMapping("/order/{orderId}")
    public ApiResponse order(@PathVariable long orderId, @RequestParam Map<String,String> query) { return read("order",orderId,query); }
    @PatchMapping("/update-status/{id}")
    public ApiResponse updateStatus(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-status",id,merged(query,body),key); }
    @PatchMapping("/update-shipping/{id}")
    public ApiResponse updateShipping(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-shipping",id,merged(query,body),key); }
    @PatchMapping("/update-receiving/{id}")
    public ApiResponse updateReceiving(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-receiving",id,merged(query,body),key); }
}

