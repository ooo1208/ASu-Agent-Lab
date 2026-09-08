package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/suppliers")
public class SuppliersController extends ErpControllerSupport {
    public SuppliersController(ErpService service) { super(service, "suppliers"); }
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
    @PatchMapping("/update-status/{id}")
    public ApiResponse updateStatus(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-status",id,merged(query,body),key); }
    @PatchMapping("/update-credit-rating/{id}")
    public ApiResponse updateCreditRating(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-credit-rating",id,merged(query,body),key); }
}

