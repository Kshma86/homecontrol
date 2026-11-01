def main():

    def connect_db():
        while running:
            conn = None
            try:
                conn = psycopg2.connect(PG_DSN)
                conn.autocommit = True
                verify_runtime_role(conn)
                print('[DB] connected')
                return conn
            except Exception as e:
                if conn is not None:
                    conn.close()
                print('[DB] connect failed, retrying in 5s:', e)
                time.sleep(5)
        raise RuntimeError('stopped while connecting DB')
