package dev.asu.erp;

public record ApiResponse(int code, String message, Object data, long timestamp) {
    public static ApiResponse ok(Object data) { return new ApiResponse(200, "success", data, System.currentTimeMillis()); }
    public static ApiResponse error(int code, String message) { return new ApiResponse(code, message, null, System.currentTimeMillis()); }
}
