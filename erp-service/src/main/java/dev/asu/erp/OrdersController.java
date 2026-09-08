package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrdersController extends ErpControllerSupport {
    public OrdersController(ErpService service) { super(service, "orders"); }
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
    @GetMapping("/details/{id}")
    public ApiResponse details(@PathVariable long id, @RequestParam Map<String,String> query) { return read("details",id,query); }
    @GetMapping("/statistics")
    public ApiResponse statistics(@RequestParam Map<String,String> query) { return read("statistics",null,query); }
    @GetMapping("/search-details")
    public ApiResponse searchDetails(@RequestParam Map<String,String> query) { return read("search-details",null,query); }
    @PatchMapping("/update-status/{id}")
    public ApiResponse updateStatus(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-status",id,merged(query,body),key); }
}

