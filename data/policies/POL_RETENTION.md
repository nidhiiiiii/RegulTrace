# Data Retention and Deletion Policy
version: 3.1

## 1. Scope
This policy covers all personal data of PayNova customers held in the user database, the data warehouse and backups.

## 2. Retention periods
controls: CTRL_ENCRYPT
KYC records are kept for 5 years after the customer relationship ends, as required under the PML Rules. Transaction records are kept for 10 years. All retained personal data is encrypted at rest.

## 3. Erasure requests
controls: CTRL_DELJOB, CTRL_ENCRYPT
When a customer withdraws consent or asks for erasure, PayNova deletes their personal data from production systems within 45 days of a verified request. Copies in backups are purged within 90 days. Encryption keys for deleted records are destroyed.

## 4. Responsibilities
Data Engineering runs the automated deletion job weekly. Security verifies key destruction monthly. Legal and Compliance reviews this policy every year.
