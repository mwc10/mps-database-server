// Why is this in assays if the template is in base?
// For passing data
$(document).ready(function () {
    // Defaults for matrix (irrelevant in matrix item)
    var reference_id_selector = $('#id_reference');
    var reference_table_selector = $('#reference_table');
    // If the data-atributes match, why bother?
    var reference_id_to_data = {};
    var current_row = null;

    // Populate reference_id_to_data
    // reference_table_selector.find('tbody').find('tr').each(function() {
    //     var current_reference_id = $(this).find('[data-reference-field=id]').text();
    //     reference_id_to_data[current_reference_id] = {};
    //     $(this).find('td').each(function() {
    //         if ($(this).attr("data-reference-field")) {
    //             reference_id_to_data[current_reference_id][$(this).attr("data-reference-field")] = $(this).text();
    //         }
    //     });
    // });

    // Open and then close dialog so it doesn't get placed in window itself
    var dialog = $('#reference_dialog');
    dialog.dialog({
        width: 900,
        height: 500,
        closeOnEscape: true,
        autoOpen: false,
        close: function() {
            $('body').removeClass('stop-scrolling');
            // update_reference_table();
        },
        open: function() {
            $('body').addClass('stop-scrolling');
        }
    });
    dialog.removeProp('hidden');

    reference_table_selector.DataTable({
        "iDisplayLength": -1,
        // Initially sort on receipt date
        "order": [ 1, "desc" ],
        // If one wants to display top and bottom
        "sDom": '<"wrapper"fti>'
    });

    // Move filter to left
    $('.dataTables_filter').css('float', 'left');

    $(document).on('click', '.open-reference-dialog', function() {
        dialog.dialog('open');
        current_row = $(this).parent().parent();
        // Get the proper selectors
        reference_id_selector = $(this).parent().find('input[readonly="readonly"]');
    });

    $(document).on('click', '.reference-selector', function() {
        var reference_id = $(this).attr('data-reference-id');
        reference_id_selector.val(reference_id);

        var current_add_row = $(this).parent().parent();

        current_row.find('[data-reference-field]').each(function() {
            $(this).text(current_add_row.find('[data-reference-field="' + $(this).attr('data-reference-field') + '"]').text());
        });

        // $.each(reference_id_to_data[reference_id], function(current_field, current_value) {
        //     var current_column = current_row.find('[data-reference-field="'+current_field+'"]');
        //     if (current_column[0]) {
        //         current_column.text(current_value);
        //     }
        // });

        dialog.dialog('close');
    });

    $(".reference-id-field").each(function() {
        var current_row = $(this).parent().parent();
        var reference_id = $(this).val();

        var current_add_row = $('.reference-selector[data-reference-id="' + reference_id + '"]').parent().parent();

        if (reference_id) {
            current_row.find('[data-reference-field]').each(function() {
                $(this).text(current_add_row.find('[data-reference-field="' + $(this).attr('data-reference-field') + '"]').text());
            });

            // $.each(reference_id_to_data[reference_id], function(current_field, current_value) {
            //     var current_column = current_row.find('[data-reference-field="'+current_field+'"]');
            //     if (current_column[0]) {
            //         current_column.text(current_value);
            //     }
            // });
        }
    });
});
