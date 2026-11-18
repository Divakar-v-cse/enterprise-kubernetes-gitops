-- One PostgreSQL instance, one database per bounded context.
-- This keeps services independently ownable without running four servers locally.
CREATE DATABASE users OWNER platform;
CREATE DATABASE products OWNER platform;
CREATE DATABASE orders OWNER platform;
CREATE DATABASE notifications OWNER platform;
