(function () {
  'use strict';

  function enhanceTables() {
    if (!window.simpleDatatables || !window.simpleDatatables.DataTable) return;
    document.querySelectorAll('table.table-striped, table.workflow-table').forEach(function (table) {
      if (table.dataset.wmsTableEnhanced || table.classList.contains('datatable') || !table.tHead) return;
      if (!table.tBodies.length || table.tBodies[0].rows.length < 2) return;
      table.dataset.wmsTableEnhanced = 'true';
      new window.simpleDatatables.DataTable(table, {
        searchable: true,
        sortable: true,
        perPage: 10,
        perPageSelect: [10, 25, 50, 100],
        labels: {
          placeholder: 'Search list...',
          perPage: 'records per page',
          noRows: 'No records found',
          info: 'Showing {start} to {end} of {rows} records'
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceTables);
  } else {
    enhanceTables();
  }
})();
