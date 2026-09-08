package dev.asu.erp;

import java.util.LinkedHashMap;
import java.util.Map;

abstract class ErpControllerSupport {
    protected final ErpService service;
    protected final String kind;
    protected ErpControllerSupport(ErpService service, String kind) { this.service = service; this.kind = kind; }
    protected ApiResponse read(String action, Long id, Map<String,String> query) { return ApiResponse.ok(service.read(kind,action,id,query)); }
    protected ApiResponse write(String action, Long id, Map<String,Object> body, String key) { return ApiResponse.ok(service.write(kind,action,id,body == null ? Map.of() : body,key)); }
    protected Map<String,Object> merged(Map<String,String> query,Map<String,Object> body) {
        Map<String,Object> result = new LinkedHashMap<>(query); if (body != null) result.putAll(body); return result;
    }
}

