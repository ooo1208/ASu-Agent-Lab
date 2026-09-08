-- Independent schema for ASu ERP. MySQL target is 8.0.16+; local tests use H2 MySQL mode.
-- Eight business tables. extra_json stores optional extension fields only.
CREATE TABLE IF NOT EXISTS erp_user (
    id BIGINT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    status INT NOT NULL CHECK (status IN (0,1)),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS erp_supplier (
    id BIGINT PRIMARY KEY,
    supplier_code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    status INT NOT NULL CHECK (status IN (0,1)),
    credit_rating VARCHAR(8) NOT NULL,
    contact_person VARCHAR(100),
    email VARCHAR(254),
    address VARCHAR(500),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS erp_part (
    id BIGINT PRIMARY KEY,
    part_code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    category VARCHAR(80) NOT NULL,
    supplier_id BIGINT NOT NULL,
    price DECIMAL(18,2) NOT NULL CHECK (price >= 0),
    unit VARCHAR(20) NOT NULL,
    status INT NOT NULL CHECK (status IN (0,1)),
    specification VARCHAR(300),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL,
    CONSTRAINT fk_part_supplier FOREIGN KEY (supplier_id) REFERENCES erp_supplier(id)
);
CREATE TABLE IF NOT EXISTS erp_purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(100) NOT NULL UNIQUE,
    total_amount DECIMAL(18,2) NOT NULL CHECK (total_amount >= 0),
    status INT NOT NULL CHECK (status BETWEEN 1 AND 5),
    order_time TIMESTAMP NOT NULL,
    expected_delivery_date DATE,
    actual_delivery_date DATE,
    created_by BIGINT,
    remark VARCHAR(2000),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL,
    CONSTRAINT fk_order_user FOREIGN KEY (created_by) REFERENCES erp_user(id)
);
CREATE TABLE IF NOT EXISTS erp_order_detail (
    order_id BIGINT NOT NULL,
    line_number INT NOT NULL,
    part_id BIGINT NOT NULL,
    supplier_id BIGINT NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(18,2) NOT NULL CHECK (unit_price >= 0),
    subtotal DECIMAL(18,2) NOT NULL CHECK (subtotal >= 0 AND subtotal = quantity * unit_price),
    remark VARCHAR(2000),
    extra_json LONGTEXT NOT NULL,
    PRIMARY KEY (order_id,line_number),
    CONSTRAINT fk_detail_order FOREIGN KEY (order_id) REFERENCES erp_purchase_order(id) ON DELETE CASCADE,
    CONSTRAINT fk_detail_part FOREIGN KEY (part_id) REFERENCES erp_part(id),
    CONSTRAINT fk_detail_supplier FOREIGN KEY (supplier_id) REFERENCES erp_supplier(id)
);
CREATE TABLE IF NOT EXISTS erp_inventory (
    id BIGINT PRIMARY KEY,
    part_id BIGINT NOT NULL UNIQUE,
    quantity BIGINT NOT NULL CHECK (quantity >= 0),
    safety_stock BIGINT NOT NULL CHECK (safety_stock >= 0),
    warehouse_location VARCHAR(160) NOT NULL,
    last_inbound_time TIMESTAMP,
    last_outbound_time TIMESTAMP,
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL,
    CONSTRAINT fk_inventory_part FOREIGN KEY (part_id) REFERENCES erp_part(id)
);
CREATE TABLE IF NOT EXISTS erp_customer (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    customer_type INT NOT NULL CHECK (customer_type BETWEEN 1 AND 3),
    discount_rate DECIMAL(5,4) NOT NULL CHECK (discount_rate BETWEEN 0 AND 1),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS erp_logistics (
    id BIGINT PRIMARY KEY,
    logistics_number VARCHAR(100) NOT NULL UNIQUE,
    order_id BIGINT NOT NULL,
    status INT NOT NULL CHECK (status BETWEEN 1 AND 4),
    logistics_company VARCHAR(160),
    tracking_number VARCHAR(160),
    shipping_date DATE,
    receiving_date DATE,
    receiver VARCHAR(100),
    remark VARCHAR(2000),
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    extra_json LONGTEXT NOT NULL,
    CONSTRAINT fk_logistics_order FOREIGN KEY (order_id) REFERENCES erp_purchase_order(id)
);
-- Foreign and unique keys provide the principal lookup indexes in MySQL.
CREATE TABLE IF NOT EXISTS erp_write_guard (id INT PRIMARY KEY);
INSERT INTO erp_write_guard (id) SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM erp_write_guard WHERE id = 1);
CREATE TABLE IF NOT EXISTS erp_sequence (kind VARCHAR(32) PRIMARY KEY, next_id BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS erp_idempotency (
    request_key VARCHAR(128) PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL,
    response_json LONGTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
