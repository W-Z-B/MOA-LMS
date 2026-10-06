"""Item 6.06: one helper hides totals for groups smaller than five in every report that leaves a course."""

from insights.smallgroups import hide_small, hide_total, too_small


def rows(*sizes):
    return [
        {"name": f"g{n}", "size": size, "marked": size, "average": "70.0"} for n, size in enumerate(sizes)
    ]


def test_a_group_smaller_than_five_has_its_figures_and_size_hidden():
    result = hide_small(rows(3, 12), size_key="size", fields=("marked", "average"))
    assert result[0] == {"name": "g0", "size": None, "marked": None, "average": None, "hidden": True}
    assert result[1]["size"] == 12 and result[1]["marked"] == 12 and result[1]["hidden"] is False


def test_five_or_more_and_nobody_at_all_are_shown():
    result = hide_small(rows(5, 0), size_key="size", fields=("marked",))
    assert [r["hidden"] for r in result] == [False, False]
    assert result[1]["size"] == 0
    assert not too_small(0) and not too_small(None) and too_small(1) and too_small(4)


def test_a_lone_hidden_row_beside_a_total_takes_the_next_smallest_with_it():
    result = hide_small(rows(2, 9, 30), size_key="size", fields=("marked",), totalled=True)
    assert [r["hidden"] for r in result] == [True, True, False]
    # Two hidden rows already cannot be told apart by subtraction: nothing more is hidden.
    result = hide_small(rows(2, 3, 9), size_key="size", fields=("marked",), totalled=True)
    assert [r["hidden"] for r in result] == [True, True, False]


def test_the_threshold_is_a_setting(settings):
    settings.REPORT_MIN_GROUP = 10
    assert hide_total({"size": 7, "marked": 7}, size_key="size", fields=("marked",))["hidden"] is True
    settings.REPORT_MIN_GROUP = 0  # never below one: a group of nobody is not hidden either way
    assert hide_total({"size": 1, "marked": 1}, size_key="size", fields=("marked",))["hidden"] is False
