package dev.asu.erp;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/statistics")
public class StatisticsController extends ErpControllerSupport {
    public StatisticsController(ErpService service) { super(service, "statistics"); }
    @GetMapping("/dashboard")
    public ApiResponse dashboard(@RequestParam Map<String,String> query) { return read("dashboard",null,query); }
    @GetMapping("/suppliers")
    public ApiResponse suppliers(@RequestParam Map<String,String> query) { return read("suppliers",null,query); }
    @GetMapping("/parts")
    public ApiResponse parts(@RequestParam Map<String,String> query) { return read("parts",null,query); }
    @GetMapping("/inventory")
    public ApiResponse inventory(@RequestParam Map<String,String> query) { return read("inventory",null,query); }
    @GetMapping("/monthly-trend")
    public ApiResponse monthlyTrend(@RequestParam Map<String,String> query) { return read("monthly-trend",null,query); }
}

