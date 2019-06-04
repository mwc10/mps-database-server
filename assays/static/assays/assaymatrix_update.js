$(document).ready(function () {
    // TODO TODO TODO IN THE FUTURE FILE-SCOPE CONSTANTS SHOULD BE IN ALL-CAPS
    // The matrix's ID
    var matrix_id = Math.floor(window.location.href.split('/')[5]);

    // FULL DATA
    var current_setup_data = [];

    // DATA FOR THE VERSION
    var current_setup = {};

    // CRUDE AND BAD
    // If I am going to use these, they should be ALL CAPS to indicate global status
    var item_prefix = 'matrix_item';
    var cell_prefix = 'cell';
    var setting_prefix = 'setting';
    var compound_prefix = 'compound';

    // The different components of a setup
    var prefixes = [
        'cell',
        'compound',
        'setting',
    ];

    var time_prefixes = [
        'addition_time',
        'duration'
    ]

    // SOMEWHAT TASTELESS USE OF VARIABLES TO TRACK WHAT IS BEING EDITED
    var current_prefix = '';
    var current_setup_index = 0;
    var current_row_index = null;
    var current_column_index = null;

    // DISPLAYS
    // JS ACCEPTS STRING LITERALS IN OBJECT INITIALIZATION
    var empty_html = {};
    var empty_compound_html = $('#empty_compound_html');
    var empty_cell_html = $('#empty_cell_html');
    var empty_setting_html = $('#empty_setting_html');
    empty_html[compound_prefix] = empty_compound_html;
    empty_html[cell_prefix] = empty_cell_html;
    empty_html[setting_prefix] = empty_setting_html;

    // TODO NEEDS TO BE REVISED
    // CREATE DIALOGS
    $.each(prefixes, function(index, prefix) {
        var current_dialog = $('#' + prefix + '_dialog');
        current_dialog.dialog({
            width: 825,
            open: function() {
                $.ui.dialog.prototype.options.open();
                // BAD
                setTimeout(function() {
                    // Blur all
                    $('.ui-dialog').find('input, select, button').blur();
                }, 250);

                // Populate the fields
                var current_data = $.extend(true, {}, current_setup_data[current_row_index][current_prefix][current_column_index]);

                console.log(current_setup_data);

                var this_popup = $(this);

                this_popup.find('input').each(function() {
                    if ($(this).attr('name')) {
                        console.log($(this).attr('name'), current_data[$(this).attr('name').replace(current_prefix + '_', '')]);
                        $(this).val(current_data[$(this).attr('name').replace(current_prefix + '_', '')]);
                    }
                });

                this_popup.find('select').each(function() {
                    if ($(this).attr('name')) {
                        console.log($(this).attr('name'), current_data[$(this).attr('name').replace(current_prefix + '_', '') + '_id']);
                        this.selectize.setValue(current_data[$(this).attr('name').replace(current_prefix + '_', '') + '_id']);
                    }
                });

                // TODO SPECIAL EXCEPTION FOR CELL SAMPLE
                this_popup.find('input[name="' + prefix + '_cell_sample"]').val(
                    current_data['cell_sample_id']
                );

                // TODO SPECIAL EXCEPTION FOR TIMES
                $.each(time_prefixes, function(index, current_time_prefix) {
                    var split_time = window.SPLIT_TIME.get_split_time(
                        current_data[current_time_prefix],
                    );

                    console.log(split_time);

                    $.each(split_time, function(time_name, time_value) {
                        console.log(prefix + '_' + current_time_prefix + '_' + time_name);
                        this_popup.find('input[name="' + prefix + '_' + current_time_prefix + '_' + time_name + '"]').val(time_value);
                    });
                });

                console.log(current_data);
            },
            buttons: [
            {
                text: 'Apply',
                click: function() {
                    // ACTUALLY MAKE THE CHANGE TO THE RESPECTIVE ENTITY
                    // TODO TODO TODO
                    var current_data = {};

                    $(this).find('input').each(function() {
                        console.log($(this).attr('name'), $(this).val());
                        if ($(this).attr('name')) {
                            current_data[$(this).attr('name').replace(current_prefix + '_', '')] = $(this).val();
                        }
                    });

                    $(this).find('select').each(function() {
                        console.log($(this).attr('name'), $(this).val());
                        if ($(this).attr('name')) {
                            current_data[$(this).attr('name').replace(current_prefix + '_', '') + '_id'] = $(this).val();
                        }
                    });

                    // SLOPPY
                    $.each(time_prefixes, function(index, current_time_prefix) {
                        if (current_data[current_time_prefix + '_minute'] !== undefined) {
                            current_data[current_time_prefix] = window.SPLIT_TIME.get_minutes(
                                    current_data[current_time_prefix + '_day'],
                                    current_data[current_time_prefix + '_hour'],
                                    current_data[current_time_prefix + '_minute']
                            );
                            $.each(window.SPLIT_TIME.time_conversions, function(key, value) {
                                delete current_data[current_time_prefix + '_' + key];
                            });
                        }
                    });

                    // Special exception for cell_sample
                    if ($(this).find('input[name="' + prefix + '_cell_sample"]')[0]) {
                        current_data['cell_sample_id'] = $(this).find('input[name="' + prefix + '_cell_sample"]').val();
                        delete current_data['cell_sample'];
                    }

                    console.log(current_data);

                    // current_setup_data[current_row_index][current_prefix][current_column_index] = $.extend(true, {}, current_data);
                    modify_setup_data(current_prefix, current_data, current_row_index, current_column_index);

                    var html_contents = get_content_display(current_prefix, current_row_index, current_column_index, current_data);

                    $('a[data-edit-button="true"][data-row="' + current_row_index +'"][data-column="' + current_column_index +'"][data-prefix="' + current_prefix + '"]').parent().html(html_contents);

                    $(this).dialog("close");
                }
            },
            {
                text: 'Cancel',
                click: function() {
                   $(this).dialog("close");
                }
            }]
        });
        current_dialog.removeProp('hidden');
    });

    function get_display_for_field(field_name, field_value, prefix) {
        // NOTE: SPECIAL EXCEPTION FOR CELL SAMPLES
        if (field_name === 'cell_sample') {
            // TODO VERY POORLY DONE
            // return $('#' + 'cell_sample_' + field_value).attr('name');
            // Global here is a little sloppy, but should always succeed
            return window.CELLS.cell_sample_id_to_label[field_value];
        }
        else {
            // Ideally, this would be cached in an object or something
            var origin = $('#id_' + prefix + '_' + field_name);

            console.log(origin);
            console.log(origin.prop('tagName'));

            // Get the select display if select
            if (origin.prop('tagName') === 'SELECT') {
                // Convert to integer if possible, thanks
                var possible_int = Math.floor(field_value);
                // console.log(possible_int);
                if (possible_int) {
                    // console.log(origin[0].selectize.options[possible_int].text);
                    return origin[0].selectize.options[possible_int].text;
                }
                else {
                    // console.log(origin[0].selectize.options[field_value].text);
                    return origin[0].selectize.options[field_value].text;
                }
                // THIS IS BROKEN, FOR PRE-SELECTIZE ERA
                // return origin.find('option[value="' + field_value + '"]').text()
            }
            // Just display the thing if there is an origin
            else if (origin[0]) {
                return field_value;
            }
            // Give back null to indicate this should not be displayed
            else {
                return null;
            }
        }
    }

    // TODO NEEDS MAJOR REVISION
    function get_content_display(prefix, row_index, column_index, content) {
        var html_contents = [
            create_edit_button(prefix, row_index, column_index)
        ];

        var new_display = empty_html[prefix].clone();

        if (content) {
            $.each(content, function(key, value) {
                // html_contents.push(key + ': ' + value);
                // I will need to think about invalid fields
                var field_name = key.replace('_id', '');
                if (field_name !== 'addition_time' && field_name !== 'duration') {
                    var field_display = get_display_for_field(field_name, value, prefix);
                    new_display.find('.' + prefix + '-' + field_name).html(field_display);
                }
                else {
                    var split_time = window.SPLIT_TIME.get_split_time(
                        value,
                    );

                    console.log(split_time);

                    $.each(split_time, function(time_name, time_value) {
                        console.log(prefix + '_' + key + '_' + time_name);
                        new_display.find('.' + prefix + '-' + key + '_' + time_name).html(time_value);
                    });
                }
            });

            html_contents.push(new_display.html());
        }

        html_contents = html_contents.join('<br>');

        return html_contents;
    }

    var number_of_columns = {
        'cell': 0,
        'compound': 0,
        'setting': 0,
    };

    // Table vars
    var study_setup_table = $('#study_setup_table');
    var study_setup_head = study_setup_table.find('thead').find('tr');
    var study_setup_body = study_setup_table.find('tbody');

    var setup_data_selector = $('#id_setup_data');

    function create_edit_button(prefix, row_index, column_index) {
        return '<a data-edit-button="true" data-row="' + row_index + '" data-prefix="' + prefix + '" data-column="' + column_index + '" role="button" class="btn btn-primary">Edit</a>';
    }

    function create_delete_button(prefix, index) {
        if (prefix === 'row') {
            return '<a data-delete-row-button="true" data-row="' + index + '" role="button" class="btn btn-danger">Delete</a>';
        }
        else {
            return '<a data-delete-column-button="true" data-column="' + index + '" data-prefix="' + prefix + '" role="button" class="btn btn-danger">Delete</a>';
        }
    }

    function create_clone_button(index) {
        return '<a data-clone-row-button="true" data-row="' + index + '" role="button" class="btn btn-info">Clone</a>';
    }

    function modify_setup_data(prefix, content, setup_index, object_index) {
        if (object_index) {
            current_setup_data[setup_index][prefix][object_index] = $.extend(true, {}, content);
        }
        else {
            current_setup_data[setup_index][prefix] = content;
        }

        setup_data_selector.val(JSON.stringify(current_setup_data));
    }

    function spawn_column(prefix) {
        var column_index = number_of_columns[prefix];
        // UGLY
        study_setup_head.find('.' + prefix + '_start').last().after('<th class="' + prefix + '_start' + '">' + prefix + ' ' + column_index + '<br>' + create_delete_button(prefix, column_index) +'</th>');

        // ADD TO EXISTING ROWS AS EMPTY
        study_setup_body.find('tr').each(function(row_index) {
            $(this).find('.' + prefix + '_start').last().after('<td class="' + prefix + '_start' + '">' + create_edit_button(prefix, row_index, column_index) + '</td>');
        });

        number_of_columns[prefix] += 1;
    }

    function populate_table_cell(prefix, content, setup_index, object_index) {

    }

    // JUST USES DEFAULT PROTOCOL FOR NOW
    function spawn_row() {
        var new_row = $('<tr>');

        var row_index = study_setup_body.find('tr').length;

        new_row.append(
            $('<td>').html(
                create_clone_button(row_index) + create_delete_button('row', row_index)
            ).append(
                $('#id_number_of_items')
                    .clone()
                    .removeAttr('id')
                    .attr('data-row', row_index)
            )
        );

        new_row.append(
            $('<td>').append(
                $('#id_test_type')
                    .clone()
                    .removeAttr('id')
                    .removeAttr('style')
                    .attr('data-row', row_index)
            )
        );

        $.each(prefixes, function(index, prefix) {
            var content_set = current_setup[prefix];
            if (!content_set.length) {
                if (!number_of_columns[prefix]) {
                    new_row.append(
                        $('<td>')
                            .attr('hidden', 'hidden')
                            .addClass(prefix + '_start')
                    );
                }
                else {
                    for (var i = 0; i < number_of_columns[prefix]; i++) {
                        new_row.append(
                            $('<td>')
                                .html(create_edit_button(prefix, row_index, i))
                                .addClass(prefix + '_start')
                        );
                    }
                }
            }
            else {
                while (number_of_columns[prefix] < content_set.length) {
                    spawn_column(prefix);
                }

                for (var i = 0; i < number_of_columns[prefix]; i++) {
                    var html_contents = get_content_display(prefix, row_index, i, content_set[i]);

                    new_row.append(
                        $('<td>')
                            .html(html_contents)
                            .addClass(prefix + '_start')
                    );
                }
            }
        });

        study_setup_body.append(new_row);

        current_setup_data.push(
            $.extend(true, {}, current_setup)
        );
        setup_data_selector.val(JSON.stringify(current_setup_data));
    }

    $(document).on('change', '.test-type', function() {
        console.log('test_type', $(this).val());
        modify_setup_data('test_type', $(this).val(), $(this).attr('data-row'));
    });

    // $(document).on('change', '.number-of-items', function() {
    //     console.log('test_type', $(this).val());
    //     modify_setup_data('number_of_items', $(this).val(), $(this).attr('data-row'));
    // });

    $(document).on('click', 'a[data-edit-button="true"]', function() {
        console.log(this);
        current_prefix = $(this).attr('data-prefix');
        current_row_index = $(this).attr('data-row');
        current_column_index = $(this).attr('data-column');
        $('#' + $(this).attr('data-prefix') + '_dialog').dialog('open');
    });

    $('a[data-add-new-button="true"]').click(function() {
        spawn_column($(this).attr('data-prefix'));
    });

    $('#add_group_button').click(function() {
        spawn_row();
    });

    // function apply_protocol_setup_to_row() {
    //
    // }

    // Handling Device flow
    // Make sure global var exists before continuing
    // ASSUMES STUDY HAS ORGAN MODEL
    // Start SPINNING
    window.spinner.spin(
        document.getElementById("spinner")
    );

  $.ajax({
      url: "/assays_ajax/",
      type: "POST",
      dataType: "json",
      data: {
          call: 'fetch_matrix_setup',
          matrix_id: matrix_id,
          csrfmiddlewaretoken: window.COOKIES.csrfmiddlewaretoken,
      },
      success: function (json) {
          // Stop spinner
          window.spinner.stop();

          console.log(json);

          current_setup = $.extend(true, {}, json.current_setup);

          // SET THE CURRENT SETUP
          // SET THE CURRENT VALUES FOR THE GROUPS
          // GENERATE THE TABLE
          // MATCH UP TRIGGERS
      },
      error: function (xhr, errmsg, err) {
          first_run = false;

          // Stop spinner
          window.spinner.stop();

          console.log(xhr.status + ": " + xhr.responseText);
      }
  });
});