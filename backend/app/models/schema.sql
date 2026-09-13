-- TriVerify schema (PostgreSQL dialect) — generated from app/models/
-- Reference only: the application creates tables itself via SQLAlchemy.
-- Regenerate:  python scripts/dump_schema.py

CREATE TABLE cases (
	case_id VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(24) NOT NULL, 
	classification VARCHAR(40), 
	overall_confidence FLOAT, 
	headline TEXT, 
	ruleset_version VARCHAR(64), 
	is_golden BOOLEAN NOT NULL, 
	source_notes JSON, 
	extraction_notes JSON, 
	PRIMARY KEY (case_id)
);

CREATE TABLE rules (
	rule_id VARCHAR(32) NOT NULL, 
	field_name VARCHAR(64), 
	rule_type VARCHAR(48) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	explanation_template TEXT NOT NULL, 
	legal_reference VARCHAR(256), 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (rule_id)
);

CREATE TABLE case_images (
	image_id VARCHAR(32) NOT NULL, 
	case_id VARCHAR(32) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	filename VARCHAR(256), 
	content_type VARCHAR(64) NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	quality_score FLOAT, 
	data BYTEA NOT NULL, 
	PRIMARY KEY (image_id), 
	FOREIGN KEY(case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);
CREATE INDEX ix_case_images_case_id ON case_images (case_id);

CREATE TABLE evidence (
	evidence_id VARCHAR(32) NOT NULL, 
	case_id VARCHAR(32) NOT NULL, 
	source_type VARCHAR(16) NOT NULL, 
	source_ref VARCHAR(512), 
	field_name VARCHAR(64), 
	raw_value TEXT, 
	normalized_value JSON, 
	bbox JSON, 
	crop_path VARCHAR(512), 
	excerpt TEXT, 
	metadata_json JSON, 
	confidence FLOAT NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (evidence_id), 
	FOREIGN KEY(case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);
CREATE INDEX ix_evidence_case_id ON evidence (case_id);
CREATE INDEX ix_evidence_field_name ON evidence (field_name);

CREATE TABLE products (
	product_id VARCHAR(32) NOT NULL, 
	case_id VARCHAR(32) NOT NULL, 
	name VARCHAR(256), 
	brand VARCHAR(128), 
	category VARCHAR(128), 
	identifier VARCHAR(128), 
	PRIMARY KEY (product_id), 
	FOREIGN KEY(case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);
CREATE INDEX ix_products_identifier ON products (identifier);
CREATE INDEX ix_products_case_id ON products (case_id);

CREATE TABLE reports (
	report_id VARCHAR(32) NOT NULL, 
	case_id VARCHAR(32) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	fmt VARCHAR(16) NOT NULL, 
	file_path VARCHAR(512), 
	content TEXT, 
	PRIMARY KEY (report_id), 
	FOREIGN KEY(case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);
CREATE INDEX ix_reports_case_id ON reports (case_id);

CREATE TABLE rule_results (
	result_id VARCHAR(32) NOT NULL, 
	case_id VARCHAR(32) NOT NULL, 
	rule_id VARCHAR(32) NOT NULL, 
	field_name VARCHAR(64), 
	status VARCHAR(20) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	explanation TEXT NOT NULL, 
	confidence FLOAT NOT NULL, 
	evidence_refs JSON, 
	ordinal INTEGER NOT NULL, 
	PRIMARY KEY (result_id), 
	FOREIGN KEY(case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);
CREATE INDEX ix_rule_results_rule_id ON rule_results (rule_id);
CREATE INDEX ix_rule_results_case_id ON rule_results (case_id);

CREATE TABLE image_observations (
	obs_id VARCHAR(32) NOT NULL, 
	product_id VARCHAR(32) NOT NULL, 
	image_path VARCHAR(512), 
	field_name VARCHAR(64) NOT NULL, 
	value_raw TEXT, 
	value_norm JSON, 
	bbox JSON, 
	confidence FLOAT NOT NULL, 
	engine VARCHAR(48), 
	PRIMARY KEY (obs_id), 
	FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE CASCADE
);
CREATE INDEX ix_image_observations_product_id ON image_observations (product_id);
CREATE INDEX ix_image_observations_field_name ON image_observations (field_name);

CREATE TABLE listing_snapshots (
	snapshot_id VARCHAR(32) NOT NULL, 
	product_id VARCHAR(32) NOT NULL, 
	source VARCHAR(64) NOT NULL, 
	url_or_id VARCHAR(512), 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	is_live BOOLEAN NOT NULL, 
	raw_json JSON, 
	PRIMARY KEY (snapshot_id), 
	FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE CASCADE
);
CREATE INDEX ix_listing_snapshots_product_id ON listing_snapshots (product_id);

CREATE TABLE official_records (
	record_id VARCHAR(32) NOT NULL, 
	product_id VARCHAR(32) NOT NULL, 
	source VARCHAR(64) NOT NULL, 
	url_or_id VARCHAR(512), 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	is_live BOOLEAN NOT NULL, 
	raw_json JSON, 
	PRIMARY KEY (record_id), 
	FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE CASCADE
);
CREATE INDEX ix_official_records_product_id ON official_records (product_id);

CREATE TABLE listing_fields (
	id SERIAL NOT NULL, 
	snapshot_id VARCHAR(32) NOT NULL, 
	field_name VARCHAR(64) NOT NULL, 
	value_raw TEXT, 
	value_norm JSON, 
	confidence FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES listing_snapshots (snapshot_id) ON DELETE CASCADE
);
CREATE INDEX ix_listing_fields_snapshot_id ON listing_fields (snapshot_id);
CREATE INDEX ix_listing_fields_field_name ON listing_fields (field_name);

CREATE TABLE official_fields (
	id SERIAL NOT NULL, 
	record_id VARCHAR(32) NOT NULL, 
	field_name VARCHAR(64) NOT NULL, 
	value_raw TEXT, 
	value_norm JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(record_id) REFERENCES official_records (record_id) ON DELETE CASCADE
);
CREATE INDEX ix_official_fields_field_name ON official_fields (field_name);
CREATE INDEX ix_official_fields_record_id ON official_fields (record_id);
