CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    password TEXT    NOT NULL,
    email    TEXT,
    role     TEXT    DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS secrets (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    key   TEXT NOT NULL,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO users (username, password, email, role) VALUES
    ('admin',   'sup3r_s3cr3t_passw0rd',   'admin@chimera.internal',   'admin'),
    ('alice',   'alice_pass_123',           'alice@chimera.internal',   'user'),
    ('bob',     'b0b_s3cur3',               'bob@chimera.internal',     'user'),
    ('charlie', 'ch4rl1e_r0cks',            'charlie@chimera.internal', 'user');

INSERT OR IGNORE INTO secrets (key, value) VALUES
    ('db_encryption_key',  'AES256-KEY-chimera-internal-2024'),
    ('internal_api_token', 'tok_internal_9f8e7d6c5b4a3210abcd'),
    ('flag',               'CHIMERA{SQLi_pwns_the_victim_service_0x41}');
