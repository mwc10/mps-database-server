$(document).ready(function() {
    $('#studyconfigurations').DataTable( {
        dom: 'T<"clear">lfrtip',
        "iDisplayLength": 50,
        "order": [[ 1, "asc" ]],
        "aoColumnDefs": [
            {
                "bSortable": false,
                "aTargets": [0]
            }
        ]
    });
});