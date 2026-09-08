package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/parts")
public class PartsController extends ErpControllerSupport {
    public PartsController(ErpService service) { super(service, "parts"); }
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
    @GetMapping("/supplier/{supplierId}")
    public ApiResponse supplier(@PathVariable long supplierId, @RequestParam Map<String,String> query) { return read("supplier",supplierId,query); }
    @PatchMapping("/update-price/{id}")
    public ApiResponse updatePrice(@PathVariable long id, @RequestParam Map<String,String> query, @RequestBody(required=false) Map<String,Object> body, @RequestHeader(name="Idempotency-Key",required=false) String key) { return write("update-price",id,merged(query,body),key); }
}

