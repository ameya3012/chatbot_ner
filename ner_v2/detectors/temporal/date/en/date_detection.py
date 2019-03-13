import datetime
import re

import ner_v2.detectors.temporal.constant as temporal_constants
from ner_v2.detectors.temporal.utils import (get_timezone, get_weekdays_for_month)


# TODO: remove date_list=None, original_list=None arguments from all sub detectors methods. Sub detectors need not see
# TODO: what other detectors have detected
class DateDetector(object):
    """
    Detects date in various formats from given text and tags them.

    Detects all date entities in given text and replaces them by entity_name.
    Additionally detect_entity() method returns detected date values in dictionary containing values for day (dd),
    month (mm), year (yy), type (exact, possible, everyday, weekend, range etc.)

    Attributes:
        text: string to extract entities from
        entity_name: string by which the detected date entities would be replaced with on calling detect_entity()
        tagged_text: string with date entities replaced with tag defined by entity name
        processed_text: string with detected date entities removed
        date: list of date entities detected
        original_date_text: list to store substrings of the text detected as date entities
        tag: entity_name prepended and appended with '__'
        timezone: Optional, pytz.timezone object used for getting current time, default is pytz.timezone('UTC')
        now_date: datetime object holding timestamp while DateDetector instantiation
        bot_message: str, set as the outgoing bot text/message

        SUPPORTED_FORMAT                                            METHOD_NAME
        ------------------------------------------------------------------------------------------------------------
        1. day/month/year                                           _gregorian_day_month_year_format
        2. month/day/year                                           _gregorian_month_day_year_format
        3. year/month/day                                           _gregorian_year_month_day_format
        4. day/month/year (Month in abbreviation or full)           _gregorian_advanced_day_month_year_format
        5. Xth month year (Month in abbreviation or full)           _gregorian_day_with_ordinals_month_year_format
        6. year month Xth (Month in abbreviation or full)           _gregorian_advanced_year_month_day_format
        7. year Xth month (Month in abbreviation or full)           _gregorian_year_day_month_format
        8. month Xth year (Month in abbreviation or full)           _gregorian_month_day_with_ordinals_year_format
        9. month Xth      (Month in abbreviation or full)           _gregorian_month_day_format
        10. Xth month      (Month in abbreviation or full)          _gregorian_day_month_format
        11."today" variants                                         _todays_date
        12."tomorrow" variants                                      _tomorrows_date
        13."yesterday" variants                                     _yesterdays_date
        14."_day_after_tomorrow" variants                           _day_after_tomorrow
        15."_day_before_yesterday" variants                         _day_before_yesterday
        16."next <day of week>" variants                            _day_in_next_week
        17."this <day of week>" variants                            _day_within_one_week
        18.probable date from only Xth                              _date_identification_given_day
        19.probable date from only Xth this month                   _date_identification_given_day_and_current_month
        20.probable date from only Xth next month                   _date_identification_given_day_and_next_month
        21."everyday" variants                                      _date_identification_everyday
        22."everyday except weekends" variants                      _date_identification_everyday_except_weekends
        23."everyday except weekdays" variants                       _date_identification_everyday_except_weekdays
        24."every monday" variants                                  _weeks_identification
        25."after n days" variants                                  _date_days_after
        26."n days later" variants                                  _date_days_later

        Not all separator are listed above. See respective methods for detail on structures of these formats

    Note:
        text and tagged_text will have a extra space prepended and appended after calling detect_entity(text)
    """

    def __init__(self, entity_name, timezone="UTC", past_date_referenced=False):
        """
        Initializes a DateDetector object with given entity_name and pytz timezone object

        Args:
            entity_name: A string by which the detected date entity substrings would be replaced with on calling
                        detect_entity()
            timezone (Optional, str): timezone identifier string that is used to create a pytz timezone object
                                      default is UTC
            past_date_referenced (bool): to know if past or future date is referenced for date text like 'kal', 'parso'

        """
        self.text = ""
        self.tagged_text = ""
        self.processed_text = ""
        self.date = []
        self.original_date_text = []
        self.entity_name = entity_name
        self.tag = "__" + entity_name + "__"
        self.timezone = get_timezone(timezone)
        self.now_date = datetime.datetime.now(tz=self.timezone)
        self.bot_message = None

        self._exact_date_detectors = [
            self._gregorian_day_month_year_format,
            self._gregorian_month_day_year_format,
            self._gregorian_year_month_day_format,
            self._gregorian_day_month_word_year_format,

            # self._day_month_format_for_arrival_departure,
            # self._date_range_ddth_of_mmm_to_ddth,
            # self._date_range_ddth_to_ddth_of_next_month,

            self._gregorian_day_with_ordinals_month_year_format,
            self._gregorian_year_month_word_day_format,
            self._gregorian_year_day_month_format,
            self._gregorian_month_day_with_ordinals_year_format,
            self._gregorian_day_month_format,
            self._gregorian_month_day_format,

            self._day_after_tomorrow,
            self._date_days_after,
            self._date_days_later,
            self._day_before_yesterday,
            self._todays_date,
            self._tomorrows_date,
            self._yesterdays_date,
            self._day_in_next_week,
            self._day_within_one_week,

            # self._day_range_for_nth_week_month,  # TODO: Wrong place or name, yields mutiple dates

            self._date_identification_given_day_and_current_month,
            self._date_identification_given_day_and_next_month,
        ]

        self._possible_date_detectors = [
            self._date_identification_given_day,

            # self._date_identification_everyday,  # takes args n_days = 15
            # self._date_identification_everyday_except_weekends,  # takes args n_days = 15
            # self._date_identification_everyday_except_weekdays,  # takes args n_days = 50

            # self._day_within_one_week,  # moved to exact
            # self._weeks_identification,  # hack for every Mon/Tues/Wednes/ ...
        ]

    def detect_date(self, text, **kwargs):
        """
        Detects exact date for complete date information - day, month, year are available in text
        and possible dates for if there are missing parts of date - day, month, year assuming sensible defaults. Also
        detects "today", "tomorrow", "yesterday", "everyday", "day after tomorrow", "day before yesterday",
        "only weekdays", "only weekends", "day in next week", "day A to day B", "month A to month B" ranges
        and their variants/synonyms

        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.
        """
        self.text = " " + text.strip().lower() + " "
        self.processed_text = self.text
        self.tagged_text = self.text

        date_list = []
        original_list = []
        date_list, original_list = self.get_exact_date(date_list, original_list)
        date_list, original_list = self.get_possible_date(date_list, original_list)
        return date_list, original_list

    def get_exact_date(self, date_list=None, original_list=None):
        """
        Detects exact date if complete date information - day, month, year are available in text.
        Also detects "today", "tomorrow", "yesterday", "day after tomorrow", "day before yesterday",
        "day in next week" and their variants/ synonyms and returns their dates as these can have exactly one date
        they refer to. Type of dates returned by this method include TYPE_NORMAL, TYPE_TODAY, TYPE_TOMORROW,
        TYPE_DAY_AFTER, TYPE_DAY_BEFORE, TYPE_YESTERDAY, TYPE_NEXT_DAY

        Args:
            date_list: Optional, list to store dictionaries of detected date entities
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities

        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """

        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []

        for detector in self._exact_date_detectors:
            date_list, original_list = detector(date_list, original_list)
            self._update_processed_text(original_list)

        return date_list, original_list

    def get_possible_date(self, date_list=None, original_list=None):
        """
        Detects possible dates for if there are missing parts of date - day, month, year assuming sensible defaults.
        Also detects "everyday","only weekdays", "only weekends","A to B" type ranges in days of week or months,
        and their variants/ synonyms and returns probable dates by using current year, month, week defaults for parts
        of dates that are missing or that include relative ranges. Type of dates returned by this method include
        TYPE_POSSIBLE_DAY, TYPE_REPEAT_DAY, TYPE_THIS_DAY, REPEAT_WEEKDAYS, REPEAT_WEEKENDS, START_RANGE, END_RANGE,
        REPEAT_START_RANGE, REPEAT_END_RANGE, DATE_START_RANGE, DATE_END_RANGE, WEEKDAYS, WEEKENDS .

        Args:
            date_list: Optional, list to store dictionaries of detected date entities
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities

        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []

        for detector in self._possible_date_detectors:
            date_list, original_list = detector(date_list, original_list)
            self._update_processed_text(original_list)

        return date_list, original_list

    def _update_processed_text(self, original_date_strings):
        """
        Replaces detected date entities with tag generated from entity_name used to initialize the object with

        A final string with all date entities replaced will be stored in object's tagged_text attribute
        A string with all date entities removed will be stored in object's processed_text attribute

        Args:
            original_date_strings: list of substrings of original text to be replaced with tag created from entity_name
        """
        for detected_text in original_date_strings:
            self.tagged_text = self.tagged_text.replace(detected_text, self.tag)
            self.processed_text = self.processed_text.replace(detected_text, '')

    def _gregorian_day_month_year_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <day><separator><month><separator><year>
        where each part is in of one of the formats given against them
            day: d, dd
            month: m, mm
            year: yy, yyyy
            separator: "/", "-", "."

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "6/2/39", "7/01/1997", "28-12-2096"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s?[/\-\.]\s?(1[0-2]|0?[1-9])'
                                   r'(?:\s?[/\-\.]\s?((?:20|19)?[0-9]{2}))?)(?:\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = int(pattern[1])
            mm = int(pattern[2])
            yy = int(self.normalize_year(pattern[3])) if pattern[3] else self.now_date.year
            if not pattern[3] and self.timezone.localize(datetime.datetime(year=yy, month=mm, day=dd)) < self.now_date:
                yy += 1

            date = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_EXACT,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date)
            original_list.append(original)
        return date_list, original_list

    def _gregorian_month_day_year_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <month><separator><day><separator><year>
        where each part is in of one of the formats given against them
            day: d, dd
            month: m, mm
            year: yy, yyyy
            separator: "/", "-", "."

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "6/2/39", "7/01/1997", "12-28-2096"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b((1[0-2]|0?[1-9])\s?[/\-\.]\s?([12][0-9]|3[01]|0?[1-9])\s?[/\-\.]'
                                   r'\s?((?:20|19)?[0-9]{2}))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[2]
            mm = pattern[1]
            yy = self.normalize_year(pattern[3])

            date = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_EXACT,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date)
            original_list.append(original)
        return date_list, original_list

    def _gregorian_year_month_day_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <year><separator><month><separator><day>
        where each part is in of one of the formats given against them
            day: d, dd
            month: m, mm
            year: yy, yyyy
            separator: "/", "-", "."

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "31/1/31", "97/2/21", "2017/12/01"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(((?:20|19)[0-9]{2})\s?[/\-\.]\s?'
                                   r'(1[0-2]|0?[1-9])\s?[/\-\.]\s?([12][0-9]|3[01]|0?[1-9]))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[3]
            mm = pattern[2]
            yy = self.normalize_year(pattern[1])

            date = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_EXACT,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date)
            original_list.append(original)
        return date_list, original_list

    def _gregorian_day_month_word_year_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <day><separator><month><separator><year>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            year: yy, yyyy
            separator: "/", "-", ".", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "21 Nov 99", "02 january 1972", "9 November 2014", "09-Nov-2014", "09/Nov/2014"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s?[\/\ \-\.\,]\s?([A-Za-z]+)\s?[\/\ \-\.\,]\s?'
                                   r'((?:20|19)?[0-9]{2}))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0].strip()
            dd = pattern[1]
            probable_mm = pattern[2]
            yy = self.normalize_year(pattern[3])
            mm = self.__get_month_index(probable_mm)
            if mm:
                date = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    },
                }
                date_list.append(date)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_day_with_ordinals_month_year_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <day><Optional ordinal inidicator><Optional "of"><separator><month><separator><year>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            year: yy, yyyy
            ordinal indicator: "st", "nd", "rd", "th", space
            separator: ",", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "21st Nov 99", "02nd of,january, 1972", "9 th November 2014", "09th Nov, 2014", "09 Nov 2014"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s?(?:nd|st|rd|th)?\s?(?:of)?[\s\,\-]\s?'
                                   r'([A-Za-z]+)[\s\,\-]\s?((?:20|19)?[0-9]{2}))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0].strip()
            dd = pattern[1]
            probable_mm = pattern[2]
            yy = self.normalize_year(pattern[3])

            mm = self.__get_month_index(probable_mm)
            if mm:
                date = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    },
                }
                date_list.append(date)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_year_month_word_day_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <year><separator><month><separator><day>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            year: yy, yyyy
            separator: "/", "-", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "2099 Nov 21", "1972 january 2", "2014 November 6", "2014-Nov-09", "2015/Nov/94"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(((?:20|19)[0-9]{2})\s?[\/\ \,\-]\s?([A-Za-z]+)\s?'
                                   r'[\/\ \,\-]\s?([12][0-9]|3[01]|0?[1-9]))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[3]
            probable_mm = pattern[2]
            yy = self.normalize_year(pattern[1])
            mm = self.__get_month_index(probable_mm)
            if mm:
                date = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    },
                }
                date_list.append(date)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_year_day_month_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <year><separator><day><Optional ordinal indicator><separator><month>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            year: yy, yyyy
            separator: ",", space
            ordinal indicator: "st", "nd", "rd", "th", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "2099 21st Nov", "1972, 2 january", "14,November,6"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(((?:20|19)[0-9]{2})[\ \,]\s?([12][0-9]|3[01]|0?[1-9])\s?'
                                   r'(?:nd|st|rd|th)?[\ \,]([A-Za-z]+))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[2]
            probable_mm = pattern[3]
            yy = self.normalize_year(pattern[1])
            mm = self.__get_month_index(probable_mm)
            if mm:
                date = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    },
                }
                date_list.append(date)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_month_day_with_ordinals_year_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <month><separator><day><Optional ordinal indicator><separator><year>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            year: yy, yyyy
            separator: ",", space
            ordinal indicator: "st", "nd", "rd", "th", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "Nov 21st 2099", "january, 2 1972", "12,November,13"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([A-Za-z]+)[\ \,\-]\s?([12][0-9]|3[01]|0?[1-9])\s?(?:nd|st|rd|th)?'
                                   r'[\ \,\-]\s?((?:20|19)?[0-9]{2}))(\s|$)')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[2]
            probable_mm = pattern[1]
            yy = self.normalize_year(pattern[3])
            mm = self.__get_month_index(probable_mm)

            if mm:
                date = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    },
                }
                date_list.append(date)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_month_day_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <month><separator><day><Optional ordinal indicator>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            separator: ",", space
            ordinal indicator: "st", "nd", "rd", "th", space

        Two character years are assumed to be belong to 21st century - 20xx.
        Only years between 1900 to 2099 are detected

        Few valid examples:
            "Feb 21st", "january, 2", "November 12"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([A-Za-z]+)[\ \,]\s?([12][0-9]|3[01]|0?[1-9])\s?(?:nd|st|rd|th)?)\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[2]
            probable_mm = pattern[1]
            mm = self.__get_month_index(probable_mm)
            if dd:
                dd = int(dd)
            if mm:
                mm = int(mm)
            if self.now_date.month > mm:
                yy = self.now_date.year + 1
            elif self.now_date.day > dd and self.now_date.month == mm:
                yy = self.now_date.year + 1
            else:
                yy = self.now_date.year
            if mm:
                date_dict = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "inferred",
                    },
                }
                date_list.append(date_dict)
                original_list.append(original)
        return date_list, original_list

    def _gregorian_day_month_format(self, date_list=None, original_list=None):
        """
        Detects date in the following format

        format: <day><Optional ordinal indicator><separator><month>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            separator: ",", space
            ordinal indicator: "st", "nd", "rd", "th", space

        Optional "of" is allowed after ordinal indicator, example "dd th of this current month"

        Few valid examples:
            "21st Nov", "2, of january ", "12th of November"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s?(?:nd|st|rd|th)?[\ \,]\s?(?:of)?\s?([A-Za-z]+))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            dd = pattern[1]
            probable_mm = pattern[2]
            mm = self.__get_month_index(probable_mm)
            if dd:
                dd = int(dd)
            if mm:
                mm = int(mm)
            if self.now_date.month > mm:
                yy = self.now_date.year + 1
            elif self.now_date.day > dd and self.now_date.month == mm:
                yy = self.now_date.year + 1
            else:
                yy = self.now_date.year
            if mm:
                date_dict = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_EXACT,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "inferred",
                    },
                }
                date_list.append(date_dict)
                original_list.append(original)
        return date_list, original_list

    def _todays_date(self, date_list=None, original_list=None):
        """
        Detects "today" and its variants and returns the date today
        Matches "today", "2dy", "2day", "tody", "aaj", "aj", "tonight"
        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b(today|2dy|2day|tody|aaj|aj|tonight)\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern
            dd = self.now_date.day
            mm = self.now_date.month
            yy = self.now_date.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_TODAY,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _tomorrows_date(self, date_list=None, original_list=None):
        """
        Detects "tommorow" and its variants and returns the date value for tommorow
        Matches "tomorrow", "2morow", "2mrw", "2mrow", "next day", "tommorrow", "tommorow", "tomorow", "tommorow"
        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.
        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b(tomm?orr?o?w|tmr?rw|tomro|2morow|2mrw|2mrr?o?w|kal|next day|'
                                   r'afte?r\s+1\s+da?y|afte?r\s+one\s+da?y|afte?r\s+a\s+da?y)\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern
            tomorrow = self.now_date + datetime.timedelta(days=1)
            dd = tomorrow.day
            mm = tomorrow.month
            yy = tomorrow.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_TOMORROW,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _yesterdays_date(self, date_list=None, original_list=None):
        """
        Detects "yesterday" and "previous day" and its variants and returns the date value for yesterday

        Matches "yesterday", "sterday", "yesterdy", "yestrdy", "yestrday", "previous day", "prev day", "prevday"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(yeste?rday|sterday|yeste?rdy|previous day|prev day|prevday)\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern
            yesterday = self.now_date - datetime.timedelta(days=1)
            dd = yesterday.day
            mm = yesterday.month
            yy = yesterday.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_YESTERDAY,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                },
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _day_after_tomorrow(self, date_list=None, original_list=None):
        """
        Detects "day after tomorrow" and its variants and returns the date on day after tomorrow
        Matches "day" or "dy" followed by "after" or "aftr" followed by one of
        "tomorrow", "2morow", "2mrw", "2mrow", "kal", "2mrrw"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b((da?y afte?r)\s+(tomm?orr?o?w|tmr?rw|tomro|2morow|2mrr?o?w|kal))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            day_after = self.now_date + datetime.timedelta(days=2)
            dd = day_after.day
            mm = day_after.month
            yy = day_after.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_DAY_AFTER,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _date_days_after(self, date_list=None, original_list=None):
        """
        Detects "date after n number of days" and returns the date after n days
        Matches "after" followed by the number of days provided
        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                               date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and type followed by the
            second list containing their corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b(afte?r\s+(\d+)\s+(da?y|da?ys))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            days = int(pattern[1])
            day_after = self.now_date + datetime.timedelta(days=days)
            dd = day_after.day
            mm = day_after.month
            yy = day_after.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_N_DAYS_AFTER,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _date_days_later(self, date_list=None, original_list=None):
        """
        Detects "date n days later" and returns the date for n days later
        Matches "digit" followed by "days" and iterations of "later"
        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                           date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and type followed by the
            second list containing their corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b((\d+)\s+(da?y|da?ys)\s?(later|ltr|latr|lter)s?)\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            days = int(pattern[1])
            day_after = self.now_date + datetime.timedelta(days=days)
            dd = day_after.day
            mm = day_after.month
            yy = day_after.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_N_DAYS_AFTER,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _day_before_yesterday(self, date_list=None, original_list=None):
        """
        Detects "day before yesterday" and its variants and returns the date on day after tomorrow

        Matches "day" or "dy" followed by "before" or "befre" followed by one of
        "yesterday", "sterday", "yesterdy", "yestrdy", "yestrday"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b((da?y befo?re)\s+(yesterday|sterday|yesterdy|yestrdy|yestrday))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            day_before = self.now_date - datetime.timedelta(days=2)
            dd = day_before.day
            mm = day_before.month
            yy = day_before.year
            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_DAY_BEFORE,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _day_in_next_week(self, date_list=None, original_list=None):
        """
        Detects "next <day of the week>" and its variants and returns the date on that day in the next week.
        Week starts with Sunday and ends with Saturday

        Matches "next" or "nxt" followed by day of the week - Sunday/Monday/Tuesday/Wednesday/Thursday/Friday/Saturday
        or their abbreviations. NOTE: Day of the week and their variants are fetched from the data store

        Example:
            If it is 7th February 2017, Tuesday while invoking this function,
            "next Sunday" would return [{'dd': 12, 'mm': 2, 'type': 'day_in_next_week', 'yy': 2017}]
            "next Saturday" would return [{'dd': 18, 'mm': 2, 'type': 'day_in_next_week', 'yy': 2017}]
            and other days would return dates between these dates

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b((ne?xt)\s+([A-Za-z]+))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            probable_day = pattern[2]
            day = self.__get_day_index(probable_day)
            current_day = self.__get_day_index(self.now_date.strftime("%A"))
            if day and current_day:
                day, current_day = int(day), int(current_day)
                date_after_days = day - current_day + 7
                day_to_set = self.now_date + datetime.timedelta(days=date_after_days)
                dd = day_to_set.day
                mm = day_to_set.month
                yy = day_to_set.year
                date_dict = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_NEXT_DAY,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    }
                }
                date_list.append(date_dict)
                original_list.append(original)
        return date_list, original_list

    def _day_within_one_week(self, date_list=None, original_list=None):
        """
        Detects "this <day of the week>" and its variants and returns the date on that day within one week from
        current date.

        Matches one of "this", "dis", "coming", "on", "for", "fr" followed by
        day of the week - Sunday/Monday/Tuesday/Wednesday/Thursday/Friday/Saturday or their abbreviations.
        NOTE: Day of the week and their variants are fetched from the data store

        Example:
            If it is 7th February 2017, Tuesday while invoking this function,
            "this Tuesday" would return [{'dd': 7, 'mm': 2, 'type': 'day_within_one_week', 'yy': 2017}]
            "for Monday" would return [{'dd': 13, 'mm': 2, 'type': 'day_within_one_week', 'yy': 2017}]
            and other days would return dates between these dates

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b((this|dis|coming|on|for)*[\s\-]*([A-Za-z]+))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0].strip()
            probable_day = pattern[2]
            day = self.__get_day_index(probable_day)
            current_day = self.__get_day_index(self.now_date.strftime("%A"))
            if day and current_day:
                day, current_day = int(day), int(current_day)
                if current_day <= day:
                    date_after_days = day - current_day
                else:
                    date_after_days = day - current_day + 7
                day_to_set = self.now_date + datetime.timedelta(days=date_after_days)
                dd = day_to_set.day
                mm = day_to_set.month
                yy = day_to_set.year
                date_dict = {
                    "dd": int(dd),
                    "mm": int(mm),
                    "yy": int(yy),
                    "type": temporal_constants.TYPE_THIS_DAY,
                    "dinfo": {
                        "dd": "detected",
                        "mm": "detected",
                        "yy": "detected",
                    }
                }
                date_list.append(date_dict)
                original_list.append(original)
        return date_list, original_list

    def _date_identification_given_day(self, date_list=None, original_list=None):
        """
        Detects probable date given only day part. The month and year are assumed to be current month and current year
        respectively. Consider checking if the returned detected date is valid.

        format: <day><Optional space><ordinal indicator>
        where each part is in of one of the formats given against them
            day: d, dd
            ordinal indicator: "st", "nd", "rd", "th"

        Example:
            If it is 7th February 2017, Tuesday while invoking this function,
            "2nd" would return [{'dd': 2, 'mm': 2, 'type': 'possible_day', 'yy': 2017}]
            "29th" would return [{'dd': 29, 'mm': 2, 'type': 'possible_day', 'yy': 2017}]
            Please note that 29/2/2017 is not a valid date on calendar but would be returned anyway as a probable date

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s*(?:nd|st|rd|th))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]

            dd = int(pattern[1])
            mm = self.now_date.month
            yy = self.now_date.year

            date = datetime.date(year=yy, month=mm, day=dd)
            if date < self.now_date.date():
                mm += 1
                if mm > 12:
                    mm = 1
                    yy += 1

            date_dict = {
                "dd": dd,
                "mm": mm,
                "yy": yy,
                "type": temporal_constants.TYPE_POSSIBLE_DAY,
                "dinfo": {
                    "dd": "detected",
                    "mm": "inferred",
                    "yy": "inferred",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _date_identification_given_day_and_current_month(self, date_list=None, original_list=None):
        """
        Detects probable date given day part and . The year is assumed to be current year
        Consider checking if the returned detected date is valid.

        Matches <day><Optional ordinal indicator><"this" or "dis"><Optional "current" or "curent"><"mnth" or "month">
        where each part is in of one of the formats given against them
            day: d, dd
            ordinal indicator: "st", "nd", "rd", "th"

        Optional "of" is allowed after ordinal indicator, example "dd th of this current month"

        Few valid examples:
            "3rd this month", "2 of this month", "05 of this current month"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.
        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s*(?:nd|st|rd|th)?\s*(?:of)?\s*(?:this|dis)\s*'
                                   r'(?:curr?ent)?\s*(mo?nth))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]

            dd = pattern[1]
            mm = self.now_date.month
            yy = self.now_date.year

            date_dict = {
                "dd": int(dd),
                "mm": int(mm),
                "yy": int(yy),
                "type": temporal_constants.TYPE_EXACT,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _date_identification_given_day_and_next_month(self, date_list=None, original_list=None):
        """
        Detects probable date given day part and "next month" synonyms. The year is assumed to be current year
        Consider checking if the returned detected date is valid.

        Matches <day><Optional ordinal indicator><"this" or "dis"><"next" variants><"mnth" or "month">
        where each part is in of one of the formats given against them
            day: d, dd
            ordinal indicator: "st", "nd", "rd", "th"
            "next" variants: "next", "nxt", "comming", "coming", "commin", "following", "folowin", "followin",
                             "folowing"

        Optional "of" is allowed after ordinal indicator, example "dd th of this next month"

        Few valid examples:
            "3rd of next month", "2 of next month", "05 of next month"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.

        """
        if date_list is None:
            date_list = []
        if original_list is None:
            original_list = []
        regex_pattern = re.compile(r'\b(([12][0-9]|3[01]|0?[1-9])\s*(?:nd|st|rd|th)?\s*(?:of)?\s*'
                                   r'(?:ne?xt|comm?ing?|foll?owing?)\s*(mo?nth))\b')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]

            dd = int(pattern[1])
            previous_mm = self.now_date.month
            yy = self.now_date.year
            mm = previous_mm + 1
            if mm > 12:
                mm = 1
                yy += 1

            date_dict = {
                "dd": dd,
                "mm": mm,
                "yy": yy,
                "type": temporal_constants.TYPE_EXACT,
                "dinfo": {
                    "dd": "detected",
                    "mm": "detected",
                    "yy": "detected",
                }
            }
            date_list.append(date_dict)
            original_list.append(original)
        return date_list, original_list

    def _day_range_for_nth_week_month(self, date_list=None, original_list=None):
        """
        Detects probable "first week of month" format and its variants and returns list of dates in those week
        and end date
        format: <ordinal><separator><week><separator><Optional "of"><month>
        where each part is in of one of the formats given against them
            day: d, dd
            month: mmm, mmmm (abbreviation or spelled out in full)
            separator: ",", space
            range separator: "to", "-", "till"

        Few valid examples:
            "first week of Jan", "second week of coming month", "last week of december"

        Args:
            date_list: Optional, list to store dictionaries of detected dates
            original_list: Optional, list to store corresponding substrings of given text which were detected as
                            date entities
        Returns:
            A tuple of two lists with first list containing the detected date entities and second list containing their
            corresponding substrings in the given text.
        """
        if original_list is None:
            original_list = []
        if date_list is None:
            date_list = []
        ordinal_choices = "|".join(temporal_constants.ORDINALS_MAP.keys())
        regex_pattern = re.compile(r'((' + ordinal_choices + r')\s+week\s+(of\s+)?([A-Za-z]+)(?:\s+month)?)\s+')
        patterns = regex_pattern.findall(self.processed_text.lower())
        for pattern in patterns:
            original = pattern[0]
            probable_mm = pattern[3]
            mm = self.__get_month_index(probable_mm)
            yy = self.now_date.year
            if mm:
                mm = int(mm)
                if self.now_date.month > mm:
                    yy += 1
            elif probable_mm in ['coming', 'comming', 'next', 'nxt', 'following', 'folowing']:
                mm = self.now_date.month + 1
                if mm > 12:
                    mm = 1
                    yy += 1
            if mm:
                weeknumber = temporal_constants.ORDINALS_MAP[pattern[1]]
                weekdays = get_weekdays_for_month(weeknumber, mm, yy)
                for day in weekdays:
                    date_dict = {
                        "dd": int(day),
                        "mm": int(mm),
                        "yy": int(yy),
                        "type": temporal_constants.TYPE_EXACT
                    }
                    date_list.append(date_dict)
                    original_list.append(original)

        return date_list, original_list

    def __get_month_index(self, value):
        # type: (str) -> Optional[int]
        """
        Gets the index of month by comparing the value with month names and their variants from the data store

        Args:
            value: string of the month detected in the text

        Returns:
            integer between 1 to 12 inclusive if value matches one of the month or its variants
            None if value doesn't match any of the month or its variants
        """
        # TODO: Make MONTH_DICT inverted index for fast lookup
        value = value.lower()
        for month in temporal_constants.MONTH_DICT:
            if value in temporal_constants.MONTH_DICT[month]:
                return month
        return None

    def __get_day_index(self, value):
        # type: (str) -> Optional[int]
        """
        Gets the index of month by comparing the value with day names and their variants from the data store

        Args:
            value: string of the month detected in the text

        Returns:
            integer between 1 to 7 inclusive if value matches one of the day or its variants
            None if value doesn't match any of the day or its variants
        """
        # TODO: Make DAY_DICT inverted index for fast lookup
        value = value.lower()
        for day in temporal_constants.DAY_DICT:
            if value in temporal_constants.DAY_DICT[day]:
                return day
        return None

    @staticmethod
    def to_date_dict(datetime_object, date_type=temporal_constants.TYPE_EXACT):
        """
        Convert the given datetime object to a dictionary containing dd, mm, yy

        Args:
            datetime_object (datetime.datetime): datetime object
            date_type (str, optional, default TYPE_EXACT): "type" metdata for this detected date

        Returns:
            dict: dictionary containing day, month, year in keys dd, mm, yy respectively with date type as additional
            metadata.
        """
        return {
            "dd": datetime_object.day,
            "mm": datetime_object.month,
            "yy": datetime_object.year,
            "type": date_type,
        }

    def to_datetime_object(self, base_date_value_dict):
        """
        Convert the given date value dict to a timezone localised datetime object

        Args:
            base_date_value_dict (dict): dict containing dd, mm, yy

        Returns:
            datetime object: datetime object localised with the timezone given on initialisation
        """
        datetime_object = datetime.datetime(year=base_date_value_dict["yy"],
                                            month=base_date_value_dict["mm"],
                                            day=base_date_value_dict["dd"], )
        return self.timezone.localize(datetime_object)

    def normalize_year(self, year):
        """
        Normalize two digit year to four digits by taking into consideration the bot message. Useful in cases like
        date of birth where past century is preferred than current. If no bot message is given it falls back to
        current century

        Args:
            year (str): Year string to normalize

        Returns:
            str: year in four digits
        """
        past_regex = re.compile(r'birth|bday|dob|born')
        present_regex = None
        future_regex = None
        this_century = int(str(self.now_date.year)[:2])
        if len(year) == 2:
            if self.bot_message:
                if past_regex and past_regex.search(self.bot_message):
                    return str(this_century - 1) + year
                elif present_regex and present_regex.search(self.bot_message):
                    return str(this_century) + year
                elif future_regex and future_regex.search(self.bot_message):
                    return str(this_century + 1) + year

        # if patterns didn't match or no bot message set, fallback to current century
        if len(year) == 2:
            return str(this_century) + year

        return year

    def set_bot_message(self, bot_message):
        """
        Sets the object's bot_message attribute

        Args:
            bot_message: is the previous message that is sent by the bot
        """
        self.bot_message = bot_message
