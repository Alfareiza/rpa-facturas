from decouple import config

from supabase import Client, create_client

CODE_ERROR_DUPLICATED_KEY = '23505'


class Supabase:

    def __init__(self):
        self.client: Client = create_client(config('SUPABASE_URL'), config('SUPABASE_KEY'))

    def insert(self, table_name: str, row: 'Record'):
        return self.client.table(table_name).insert(row.as_dict).execute()

    def update(self, table_name: str, row: 'Record', **updates: dict):
        query = self.client.table(table_name).update(updates)
        for column, value in row.as_dict.items():
            if value:
                query = query.eq(column, value)
        return query.execute()

    def delete(self, table_name: str, row: 'Record'):
        """Fetches data from Supabase table."""
        query = self.client.table(table_name).delete()
        for column, value in row.as_dict.items():
            query = query.eq(column, value)
        return query.execute()

    def fetch(self, table_name: str, columns: None = str, filter_eq: list = []):
        """Fetches data from Supabase table."""
        query = self.client.table(table_name).select(columns or "*")
        for column, value in filter_eq:
            query = query.eq(column, value)
        return query.execute()


if __name__ == '__main__':
    ...
