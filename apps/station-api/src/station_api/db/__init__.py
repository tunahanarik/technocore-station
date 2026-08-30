"""Local SQLite persistence.

WAL journal mode and foreign key enforcement are applied on every connection.
No table in this schema holds a seed, private key or any other secret.
"""
