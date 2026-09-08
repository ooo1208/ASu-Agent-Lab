package dev.asu.erp;

public class ApiException extends RuntimeException {
    final int status;
    public ApiException(int status, String message) { super(message); this.status = status; }
    static ApiException bad(String message) { return new ApiException(400, message); }
    static ApiException conflict(String message) { return new ApiException(409, message); }
}
