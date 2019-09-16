#!/usr/bin/python

from __future__ import absolute_import, print_function

import os
import sqlite3
import sys


class Sqlite_db():
    '''
    Wrapper for sqlite3 that includes some budget error/exception handling.
    Usage:
        Sqlite_db.connect(db)
            Tries to connect, if connection doesn't already exist
        Sqlite_db.query('SELECT something FROM table', fetch=False)
            Makes the query against the database.
                fetch=True will return selected items.
                Otherwise query is made as supplied
        Sqlite_db.commit_change()
            Commits changes made to the database.
        Sqlite_db.disconnect(db)
            Tries to disconnect.
    '''
    connection = ''
    c = ''

    def connect(self, db):
        try:
            self.connection.execute("")
        except Exception:
            try:
                self.connection = sqlite3.connect(db)
                self.c = self.connection.cursor()
            except Exception:
                raise
                sys.exit(1)

    def disconnect(self, db):
        try:
            self.connection.execute("")
            try:
                self.connection.close()
                try:
                    self.connection.execute("")
                except Exception:
                    raise
            except Exception:
                raise
        except Exception:
            pass

    def query(self, query_string, fetch=False):
        try:
            self.c.execute(query_string)
            if not fetch:
                self.c.execute(query_string)
            else:
                self.c.execute(query_string)
                return self.c.fetchall()
        except Exception:
            raise


class ReadTCC():
    def __init__(self, tcc_db_path):
        self.tcc_db = tcc_db_path.rstrip('/')
        self.tcc_db = os.path.expandvars(self.tcc_db)
        self.tcc_db = os.path.expanduser(self.tcc_db)
        self.sqlite = Sqlite_db()

    def read_db(self):
        if self.tcc_db.startswith('/Library') and os.getuid() != 0:
            print('You must be root to read {}'.format(self.tcc_db))
            sys.exit(1)
        else:
            self.sqlite.connect(self.tcc_db)
            query = self.sqlite.query('SELECT service, client FROM access', fetch=True)
            if query:
                print('-----------------------------------------------------------------------')
                print(' {:<35} | {}'.format('Service', 'Client'))
                print('-----------------------------------------------------------------------')
                for service, client in query:
                    print((' {:<35} | {}'.format(service, client)))
            self.sqlite.disconnect(self.tcc_db)


def main():
    if len(sys.argv) is 2:
        try:
            tcc_db = os.path.expandvars(sys.argv[1])
            tcc_db = os.path.expanduser(tcc_db)

            if os.path.exists(tcc_db) and 'TCC.db' in tcc_db:
                tcc = ReadTCC(tcc_db_path=tcc_db)
                tcc.read_db()
            else:
                print('Please specify the TCC path to read. Either "/Library/Application Support/com.apple.TCC/TCC.db" or "~/Library/Application Support/com.apple.TCC/TCC.db"')
                sys.exit(1)
        except Exception:
            raise
    else:
        print('Please specify the TCC path to read. Either "/Library/Application Support/com.apple.TCC/TCC.db" or "~/Library/Application Support/com.apple.TCC/TCC.db"')
        sys.exit(1)


if __name__ == '__main__':
    main()
