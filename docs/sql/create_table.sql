-- SmartCopilot MySQL schema.
-- Execute this file against the SmartCopilot database.
-- Table creation order follows foreign-key dependencies.

CREATE TABLE IF NOT EXISTS users (
  id INT NOT NULL AUTO_INCREMENT,
  username VARCHAR(255) NOT NULL,
  password VARCHAR(255) NOT NULL,
  role ENUM('USER', 'ADMIN') NOT NULL DEFAULT 'USER',
  org_tags VARCHAR(1000) NULL,
  primary_org VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY idx_users_username (username),
  KEY idx_users_role (role),
  KEY idx_users_primary_org (primary_org)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS organization_tags (
  tag_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT NULL,
  parent_tag VARCHAR(255) NULL,
  upload_max_size_bytes BIGINT NULL,
  created_by INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (tag_id),
  KEY idx_organization_tags_parent_tag (parent_tag),
  KEY idx_organization_tags_created_by (created_by),
  CONSTRAINT fk_organization_tags_created_by
    FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS file_upload (
  id BIGINT NOT NULL AUTO_INCREMENT,
  file_md5 VARCHAR(32) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  total_size BIGINT NOT NULL,
  status INT NOT NULL DEFAULT 0,
  user_id VARCHAR(64) NOT NULL,
  org_tag VARCHAR(255) NULL,
  is_public TINYINT(1) NOT NULL DEFAULT 0,
  estimated_embedding_tokens BIGINT NULL,
  estimated_chunk_count INT NULL,
  actual_embedding_tokens BIGINT NULL,
  actual_chunk_count INT NULL,
  vectorization_status VARCHAR(32) NULL,
  vectorization_error_message VARCHAR(1000) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  merged_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_file_upload_md5_user (file_md5, user_id),
  KEY idx_file_upload_file_md5 (file_md5),
  KEY idx_file_upload_user_id (user_id),
  KEY idx_file_upload_org_tag (org_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chunk_info (
  id BIGINT NOT NULL AUTO_INCREMENT,
  file_md5 VARCHAR(32) NOT NULL,
  chunk_index INT NOT NULL,
  chunk_md5 VARCHAR(32) NOT NULL,
  storage_path VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_file_md5_chunk_index (file_md5, chunk_index),
  KEY idx_chunk_info_file_md5 (file_md5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_vectors (
  vector_id BIGINT NOT NULL AUTO_INCREMENT,
  file_md5 VARCHAR(32) NOT NULL,
  chunk_id INT NOT NULL,
  text_content LONGTEXT NOT NULL,
  page_number INT NULL,
  anchor_text VARCHAR(512) NULL,
  model_version VARCHAR(32) NULL,
  user_id VARCHAR(64) NOT NULL,
  org_tag VARCHAR(50) NULL,
  is_public TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (vector_id),
  KEY idx_document_vectors_file_md5 (file_md5),
  KEY idx_document_vectors_user_id (user_id),
  KEY idx_document_vectors_org_tag (org_tag),
  UNIQUE KEY uk_document_vectors_file_chunk (file_md5, chunk_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversation_sessions (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  conversation_id VARCHAR(64) NOT NULL,
  title VARCHAR(255) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY idx_conversation_sessions_conversation_id (conversation_id),
  KEY idx_conversation_sessions_user_id (user_id),
  KEY idx_conversation_sessions_status (status),
  CONSTRAINT fk_conversation_sessions_user
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversations (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  conversation_id VARCHAR(64) NULL,
  reference_mappings_json TEXT NULL,
  timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_conversations_user_id (user_id),
  KEY idx_conversations_timestamp (timestamp),
  KEY idx_conversations_conversation_id (conversation_id),
  CONSTRAINT fk_conversations_user
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_memories (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  content TEXT NOT NULL,
  memory_type VARCHAR(40) NOT NULL DEFAULT 'fact',
  source_conversation_id VARCHAR(64) NULL,
  confidence FLOAT NOT NULL DEFAULT 0.7,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_user_memories_user_id (user_id),
  KEY idx_user_memories_type (memory_type),
  KEY idx_user_memories_status (status),
  KEY idx_user_memories_conversation_id (source_conversation_id),
  CONSTRAINT fk_user_memories_user
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_token_records (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  record_date DATE NOT NULL,
  token_type ENUM('LLM', 'EMBEDDING') NOT NULL,
  change_type ENUM('INCREASE', 'CONSUME') NOT NULL,
  amount BIGINT NOT NULL,
  balance_before BIGINT NULL,
  balance_after BIGINT NULL,
  reason VARCHAR(255) NULL,
  remark TEXT NULL,
  request_count INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_user_token_records_user_id (user_id),
  KEY idx_user_token_records_type (token_type, change_type),
  KEY idx_user_token_records_date (record_date),
  CONSTRAINT fk_user_token_records_user
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recharge_packages (
  id INT NOT NULL AUTO_INCREMENT,
  package_name VARCHAR(100) NOT NULL,
  package_price BIGINT NOT NULL,
  package_desc TEXT NULL,
  package_benefit TEXT NULL,
  llm_token BIGINT NOT NULL DEFAULT 0,
  embedding_token BIGINT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  deleted TINYINT(1) NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_recharge_packages_enabled (enabled, deleted),
  KEY idx_recharge_packages_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recharge_orders (
  id BIGINT NOT NULL AUTO_INCREMENT,
  trade_no VARCHAR(64) NOT NULL,
  user_id INT NOT NULL,
  package_id INT NULL,
  amount BIGINT NOT NULL,
  llm_token BIGINT NOT NULL DEFAULT 0,
  embedding_token BIGINT NOT NULL DEFAULT 0,
  wx_transaction_id VARCHAR(128) NULL,
  status ENUM('NOT_PAY', 'PAYING', 'SUCCEED', 'FAIL', 'CANCELLED') NOT NULL DEFAULT 'NOT_PAY',
  description TEXT NULL,
  pay_time DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY idx_recharge_orders_trade_no (trade_no),
  KEY idx_recharge_orders_user_id (user_id),
  KEY idx_recharge_orders_status (status),
  KEY idx_recharge_orders_package_id (package_id),
  CONSTRAINT fk_recharge_orders_user
    FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_recharge_orders_package
    FOREIGN KEY (package_id) REFERENCES recharge_packages(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_model_preferences (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  model_mode ENUM('FREE', 'PAID', 'CUSTOM') NOT NULL DEFAULT 'FREE',
  custom_base_url VARCHAR(500) NULL,
  custom_model VARCHAR(255) NULL,
  custom_api_key_encrypted TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY idx_user_model_preferences_user_id (user_id),
  CONSTRAINT fk_user_model_preferences_user
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
