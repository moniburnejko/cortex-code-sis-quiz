-- SNOWPRO QUIZ APP — SETUP SCRIPT
-- Run once before the first Cortex Code session
-- Replace <warehouse>, <database>, <schema> with your values
-- See SETUP.md for step-by-step guidance


-- STEP 1: cross-region inference (ACCOUNTADMIN required)
-- Required for accounts outside AWS US regions
-- Without this, AI_COMPLETE fails for claude models

USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';

-- verify:
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
-- expected: value = AWS_US


-- STEP 2: role (SECURITYADMIN)

USE ROLE SECURITYADMIN;

CREATE ROLE IF NOT EXISTS CORTEXADMIN;
GRANT ROLE CORTEXADMIN TO ROLE SYSADMIN;


-- STEP 3: warehouse (SYSADMIN)

USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS <warehouse>
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 120
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;


-- STEP 4: database and schema (SYSADMIN)
-- Each exam uses a dedicated schema — never share a schema between exams.
-- Recommended naming: QUIZ_<EXAM_CODE>, e.g. QUIZ_COF_C03, GES-C01
-- This ensures tables, stages, and Streamlit apps are fully isolated per exam.

USE ROLE SYSADMIN;

CREATE DATABASE IF NOT EXISTS <database>;
CREATE SCHEMA IF NOT EXISTS <database>.<schema>;   -- e.g. QUIZ_COF_C03


-- STEP 5: grants

USE ROLE SECURITYADMIN;

GRANT DATABASE ROLE SNOWFLAKE.COPILOT_USER TO ROLE CORTEXADMIN;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE CORTEXADMIN;

USE ROLE SYSADMIN;

GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE CORTEXADMIN;
GRANT OPERATE ON WAREHOUSE <warehouse> TO ROLE CORTEXADMIN;

GRANT USAGE ON DATABASE <database> TO ROLE CORTEXADMIN;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;

GRANT CREATE TABLE ON SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;
GRANT CREATE STAGE ON SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;
GRANT CREATE FILE FORMAT ON SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;
GRANT CREATE STREAMLIT ON SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;

GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;
GRANT READ, WRITE ON FUTURE STAGES IN SCHEMA <database>.<schema> TO ROLE CORTEXADMIN;


-- STEP 6: verify (run as CORTEXADMIN)

USE ROLE CORTEXADMIN;
USE WAREHOUSE <warehouse>;
USE DATABASE <database>;
USE SCHEMA <schema>;

SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
-- all four columns should return the expected values