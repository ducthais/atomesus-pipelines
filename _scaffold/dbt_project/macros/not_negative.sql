{# Test `not_negative` của Spec (transform.tests[].test). #}
{% test not_negative(model, column_name) %}
select {{ column_name }} from {{ model }} where {{ column_name }} < 0
{% endtest %}
