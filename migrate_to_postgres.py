import sqlite3
import psycopg2
import os
from psycopg2.extras import execute_values

# ПОДКЛЮЧЕНИЯ
# SQLite (ваш текущий файл)
sqlite_conn = sqlite3.connect('phrases.db')
sqlite_cursor = sqlite_conn.cursor()

# PostgreSQL (замените на вашу строку от Neon/Vercel Postgres)
# Получить можно здесь: Vercel → Storage → ваша база → Connection String
POSTGRES_URL = postgresql://neondb_owner:npg_GiAonOXe4s6h@ep-old-brook-aldh2xp9-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
postgres_conn = psycopg2.connect(POSTGRES_URL)
postgres_cursor = postgres_conn.cursor()


def migrate_table(table_name):
    """Переносит одну таблицу из SQLite в PostgreSQL"""

    # 1. Получаем структуру таблицы из SQLite
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns = sqlite_cursor.fetchall()
    col_names = [col[1] for col in columns]
    col_types = [col[2] for col in columns]

    # 2. Создаём такую же таблицу в PostgreSQL
    create_query = f"CREATE TABLE IF NOT EXISTS {table_name} ("
    for col_name, col_type in zip(col_names, col_types):
        # Конвертируем типы SQLite в PostgreSQL
        pg_type = 'TEXT' if col_type == 'TEXT' else 'INTEGER' if col_type in (
        'INTEGER', 'BOOLEAN') else 'TIMESTAMP' if 'TIMESTAMP' in col_type.upper() else 'FLOAT'
        create_query += f"{col_name} {pg_type}, "
    create_query = create_query.rstrip(', ') + ")"

    postgres_cursor.execute(create_query)

    # 3. Переносим данные
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()

    if rows:
        placeholders = ','.join(['%s'] * len(col_names))
        insert_query = f"INSERT INTO {table_name} ({','.join(col_names)}) VALUES %s"
        execute_values(postgres_cursor, insert_query, rows)

    print(f"✅ Таблица '{table_name}': перенесено {len(rows)} строк")
    postgres_conn.commit()


# 4. Получаем список всех таблиц в SQLite
sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = sqlite_cursor.fetchall()

print(f"📊 Найдено таблиц: {len(tables)}")
for table in tables:
    table_name = table[0]
    migrate_table(table_name)

# 5. Закрываем соединения
sqlite_conn.close()
postgres_conn.close()

print("\n🎉 Миграция завершена!")