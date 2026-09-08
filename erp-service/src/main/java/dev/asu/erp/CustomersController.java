package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/customers")
public class CustomersController extends ErpControllerSupport {
    public CustomersController(ErpService service) { super(service, "customers"); }
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
    @GetMapping("/search")
    public ApiResponse search(@RequestParam Map<String,String> query) { return read("search",null,query); }
    @PatchMapping("/update-type/{id}")
    public ApiResponse updateType(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-type",id,merged(query,body),key); }
    @PatchMapping("/update-discount/{id}")
    public ApiResponse updateDiscount(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-discount",id,merged(query,body),key); }
}

