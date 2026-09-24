from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from tests.test_phase2_schema import EXPECTED_DOMAIN_TABLES


class MigrationRoundTripTests(TransactionTestCase):
    def test_all_domain_migrations_rollback_and_reapply(self):
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()
        zero_targets = [(app_label, None) for app_label, _ in leaf_nodes]

        executor.migrate(zero_targets)
        tables_after_rollback = set(connection.introspection.table_names())
        self.assertTrue(EXPECTED_DOMAIN_TABLES.isdisjoint(tables_after_rollback))

        executor = MigrationExecutor(connection)
        executor.migrate(leaf_nodes)
        tables_after_apply = set(connection.introspection.table_names())
        self.assertTrue(EXPECTED_DOMAIN_TABLES.issubset(tables_after_apply))
