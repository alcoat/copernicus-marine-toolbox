from datetime import datetime, timezone

from freezegun import freeze_time

from copernicusmarine.core_functions.utils import (
    datetime_parser,
    timestamp_parser,
)


class TestUtilityFunctions:
    @freeze_time("2012-01-14 03:21:34", tz_offset=-2)
    def test_datetime_parser(self):
        # all parsed dates are in UTC
        assert datetime_parser("now") == datetime(
            2012, 1, 14, 1, 21, 34, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14T03:21:34.000000+02:00") == datetime(
            2012, 1, 14, 1, 21, 34, tzinfo=timezone.utc
        )

        # All format are supported
        assert datetime_parser("2012") == datetime(
            2012, 1, 1, 0, 0, 0, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14") == datetime(
            2012, 1, 14, 0, 0, 0, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14T03:21:34") == datetime(
            2012, 1, 14, 3, 21, 34, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14 03:21:34") == datetime(
            2012, 1, 14, 3, 21, 34, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14T03:21:34.000000") == datetime(
            2012, 1, 14, 3, 21, 34, tzinfo=timezone.utc
        )
        assert datetime_parser("2012-01-14T03:21:34.000000Z") == datetime(
            2012, 1, 14, 3, 21, 34, tzinfo=timezone.utc
        )

    def test_timestamp_parser(self):
        assert timestamp_parser(-630633600000) == datetime(
            1950, 1, 7, 0, 0, 0, tzinfo=timezone.utc
        )
        assert timestamp_parser(0) == datetime(
            1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc
        )
        assert timestamp_parser(1672527600000) == datetime(
            2022, 12, 31, 23, 0, 0, tzinfo=timezone.utc
        )
        assert timestamp_parser(1672527600, unit="s") == datetime(
            2022, 12, 31, 23, 0, 0, tzinfo=timezone.utc
        )
