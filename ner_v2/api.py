# -*- coding: utf-8 -*-
from chatbot_ner.config import ner_logger
from ner_constants import PARAMETER_MESSAGE, PARAMETER_ENTITY_NAME, PARAMETER_STRUCTURED_VALUE, \
    PARAMETER_FALLBACK_VALUE, \
    PARAMETER_BOT_MESSAGE, PARAMETER_TIMEZONE, PARAMETER_LANGUAGE_SCRIPT, PARAMETER_SOURCE_LANGUAGE, \
    PARAMETER_PAST_DATE_REFERENCED, PARAMETER_MIN_DIGITS, PARAMETER_MAX_DIGITS, PARAMETER_NUMBER_UNIT_TYPE

from ner_v2.detectors.temporal.date.date_detection import DateAdvancedDetector
from ner_v2.detectors.temporal.time.time_detection import TimeDetector
from ner_v2.detectors.numeral.number.number_detection import NumberDetector
from ner_v2.detectors.numeral.number_range.number_range_detection import NumberRangeDetector
from language_utilities.constant import ENGLISH_LANG
from ner_v2.detectors.pattern.phone_number.phone_number_detection import PhoneDetector

from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import json
import six


def get_parameters_dictionary(request):
    """Returns the list of parameters require for NER

        Params
            request (HttpResponse)
                HTTP response from url
        Returns
           parameters_dict (json)
                parameter dictionary
    """
    parameters_dict = {PARAMETER_MESSAGE: request.GET.get('message'),
                       PARAMETER_ENTITY_NAME: request.GET.get('entity_name'),
                       PARAMETER_STRUCTURED_VALUE: request.GET.get('structured_value'),
                       PARAMETER_FALLBACK_VALUE: request.GET.get('fallback_value'),
                       PARAMETER_BOT_MESSAGE: request.GET.get('bot_message'),
                       PARAMETER_TIMEZONE: request.GET.get('timezone'),
                       PARAMETER_LANGUAGE_SCRIPT: request.GET.get('language_script', ENGLISH_LANG),
                       PARAMETER_SOURCE_LANGUAGE: request.GET.get('source_language', ENGLISH_LANG),
                       PARAMETER_PAST_DATE_REFERENCED: request.GET.get('date_past_reference', 'False'),
                       PARAMETER_MIN_DIGITS: request.GET.get('min_number_digits'),
                       PARAMETER_MAX_DIGITS: request.GET.get('max_number_digits'),
                       PARAMETER_NUMBER_UNIT_TYPE: request.GET.get('unit_type'),
                       }

    return parameters_dict


def parse_post_request(request):
    # type: (django.http.HttpRequest) -> Dict[str, Any]
    """
    Extract POST request body from HTTP request

    Args:
        request (django.http.HttpRequest): HTTP response from url

    Returns:
       dict: parameters from the request
    """
    request_data = json.loads(request.body)
    parameters_dict = {
        PARAMETER_MESSAGE: request_data.get('message'),
        PARAMETER_ENTITY_NAME: request_data.get('entity_name'),
        PARAMETER_STRUCTURED_VALUE: request_data.get('structured_value'),
        PARAMETER_FALLBACK_VALUE: request_data.get('fallback_value'),
        PARAMETER_BOT_MESSAGE: request_data.get('bot_message'),
        PARAMETER_TIMEZONE: request_data.get('timezone'),
        PARAMETER_LANGUAGE_SCRIPT: request_data.get('language_script', ENGLISH_LANG),
        PARAMETER_SOURCE_LANGUAGE: request_data.get('source_language', ENGLISH_LANG),
        PARAMETER_MIN_DIGITS: request_data.get('min_number_digits'),
        PARAMETER_MAX_DIGITS: request_data.get('max_number_digits'),
        PARAMETER_NUMBER_UNIT_TYPE: request_data.get('unit_type')
    }

    return parameters_dict


@csrf_exempt
def date(request):
    """This functionality use DateAdvanceDetector to detect date. It is called through api call

    Args:
        request (django.http.request.HttpRequest): HttpRequest object

        request params:
            message (str): natural text on which detection logic is to be run. Note if structured value is present
                                   detection is run on structured value instead of message
            entity_name (str): name of the entity. Also acts as elastic-search dictionary name
                              if entity uses elastic-search lookup
            structured_value (str): Value obtained from any structured elements. Note if structured value is present
                                   detection is run on structured value instead of message
                                   (For example, UI elements like form, payload, etc)
            fallback_value (str): If the detection logic fails to detect any value either from structured_value
                             or message then we return a fallback_value as an output.
            bot_message (str): previous message from a bot/agent.
            timezone (str): timezone of the user
            source_language (str): source language code (ISO 639-1)
            language_script (str): language code of script (ISO 639-1)

    Returns:
        response (django.http.response.HttpResponse): HttpResponse object

    Example:

           message = "agle mahine k 5 tarikh ko mera birthday hai"
           entity_name = 'time'
           structured_value = None
           fallback_value = None
           bot_message = None
           timezone = 'UTC'
           source_language = 'hi'
           language_script = 'en'
           output = date(request)
           print output

           >>  [{'detection': 'message', 'original_text': 'agle mahine k 5 tarikh',
                 'entity_value': {'value': {'mm': 12, 'yy': 2018, 'dd': 5, 'type': 'date'}}}]
    """
    try:
        parameters_dict = {}
        if request.method == "POST":
            parameters_dict = parse_post_request(request)
            ner_logger.debug('Start Bulk Detection: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        elif request.method == "GET":
            parameters_dict = get_parameters_dictionary(request)
            ner_logger.debug('Start: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])

        timezone = parameters_dict[PARAMETER_TIMEZONE] or 'UTC'
        date_past_reference = parameters_dict.get(PARAMETER_PAST_DATE_REFERENCED, "false")
        past_date_referenced = date_past_reference == 'true' or date_past_reference == 'True'
        date_detection = DateAdvancedDetector(entity_name=parameters_dict[PARAMETER_ENTITY_NAME],
                                              language=parameters_dict[PARAMETER_SOURCE_LANGUAGE],
                                              timezone=timezone,
                                              past_date_referenced=past_date_referenced)

        date_detection.set_bot_message(bot_message=parameters_dict[PARAMETER_BOT_MESSAGE])

        message = parameters_dict[PARAMETER_MESSAGE]
        entity_output = None

        if isinstance(message, six.string_types):
            entity_output = date_detection.detect(message=message,
                                                  structured_value=parameters_dict[PARAMETER_STRUCTURED_VALUE],
                                                  fallback_value=parameters_dict[PARAMETER_FALLBACK_VALUE]
                                                  )
        elif isinstance(message, (list, tuple)):
            entity_output = date_detection.detect_bulk(messages=message)

        ner_logger.debug('Finished %s : %s ' % (parameters_dict[PARAMETER_ENTITY_NAME], entity_output))
    except TypeError as e:
        ner_logger.exception('Exception for date: %s ' % e)
        return HttpResponse(status=500)

    return HttpResponse(json.dumps({'data': entity_output}), content_type='application/json')


@csrf_exempt
def time(request):
    """This functionality use TimeDetector to detect time. It is called through api call

    Args:
        request (django.http.request.HttpRequest): HttpRequest object

        request params:
            message (str): natural text on which detection logic is to be run. Note if structured value is present
                                   detection is run on structured value instead of message
            entity_name (str): name of the entity. Also acts as elastic-search dictionary name
                              if entity uses elastic-search lookup
            structured_value (str): Value obtained from any structured elements. Note if structured value is present
                                   detection is run on structured value instead of message
                                   (For example, UI elements like form, payload, etc)
            fallback_value (str): If the detection logic fails to detect any value either from structured_value
                             or message then we return a fallback_value as an output.
            bot_message (str): previous message from a bot/agent.
            timezone (str): timezone of the user
            source_language (str): source language code (ISO 639-1)
            language_script (str): language code of script (ISO 639-1)

    Returns:
        response (django.http.response.HttpResponse): HttpResponse object

    Example:

           message = "kal subah 5 baje mujhe jaga dena"
           entity_name = 'time'
           structured_value = None
           fallback_value = None
           bot_message = None
           timezone = 'UTC'
           source_language = 'hi'
           language_script = 'en'
           output = time(request)
           print output

           >>  [{'detection': 'message', 'original_text': '12:30 pm',
                'entity_value': {'mm': 30, 'hh': 12, 'nn': 'pm'}}]
    """
    try:
        parameters_dict = {}
        if request.method == "POST":
            parameters_dict = parse_post_request(request)
            ner_logger.debug('Start Bulk Detection: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        elif request.method == "GET":
            parameters_dict = get_parameters_dictionary(request)
            ner_logger.debug('Start: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])

        timezone = parameters_dict[PARAMETER_TIMEZONE] or 'UTC'
        form_check = True if parameters_dict[PARAMETER_STRUCTURED_VALUE] else False
        time_detection = TimeDetector(entity_name=parameters_dict[PARAMETER_ENTITY_NAME],
                                      language=parameters_dict[PARAMETER_SOURCE_LANGUAGE],
                                      timezone=timezone)

        time_detection.set_bot_message(bot_message=parameters_dict[PARAMETER_BOT_MESSAGE])

        message = parameters_dict[PARAMETER_MESSAGE]
        entity_output = None

        if isinstance(message, six.string_types):
            entity_output = time_detection.detect(message=message,
                                                  structured_value=parameters_dict[PARAMETER_STRUCTURED_VALUE],
                                                  fallback_value=parameters_dict[PARAMETER_FALLBACK_VALUE],
                                                  form_check=form_check)
        elif isinstance(message, (list, tuple)):
            entity_output = time_detection.detect_bulk(messages=message)

        ner_logger.debug('Finished %s : %s ' % (parameters_dict[PARAMETER_ENTITY_NAME], entity_output))
    except TypeError as e:
        ner_logger.exception('Exception for time: %s ' % e)
        return HttpResponse(status=500)

    return HttpResponse(json.dumps({'data': entity_output}), content_type='application/json')


@csrf_exempt
def number(request):
    """Use NumberDetector to detect numerals

       Attributes:
        request: url parameters:

        request params:
           message (str): natural text on which detection logic is to be run. Note if structured value is
                                   detection is run on structured value instead of message
           entity_name (str): name of the entity. Also acts as elastic-search dictionary name
                              if entity uses elastic-search lookup
           structured_value (str): Value obtained from any structured elements. Note if structured value is
                                   detection is run on structured value instead of message
                                   (For example, UI elements like form, payload, etc)
           fallback_value (str): If the detection logic fails to detect any value either from structured_value
                             or message then we return a fallback_value as an output.
           bot_message (str): previous message from a bot/agent.
           unit_type(str): restrict number range to detect for some unit types like 'currency', 'temperature'

           min_digit (str): min digit
           max_digit (str): max digit


       Returns:
           dict or None: dictionary containing entity_value, original_text and detection;
                         entity_value is in itself a dict with its keys varying from entity to entity

       Example:

           message = "I want to purchase 30 units of mobile and 40 units of Television"
           entity_name = 'number_of_unit'
           structured_value = None
           fallback_value = None
           bot_message = None
           unit_type = None
           output = get_number(message=message, entity_name=entity_name, structured_value=structured_value,
                              fallback_value=fallback_value, bot_message=bot_message, min_digit=1, max_digit=2)
           print output

               >> [{'detection': 'message', 'original_text': '30', 'entity_value': {'value': '30', 'unit': None}},
                   {'detection': 'message', 'original_text': '40', 'entity_value': {'value': '40', 'unit': None}}]


           message = "I want to reserve a table for 3 people"
           entity_name = 'number_of_people'
           structured_value = None
           fallback_value = None
           bot_message = None
           unit_type = None
           min_digit=1
           max_digit=6
           output = number(request)
           print output

               >> [{'detection': 'message', 'original_text': 'for 3 people', 'entity_value':
                                                                        {'value': '3', 'unit': 'people'}}]

       """
    try:
        parameters_dict = {}
        if request.method == "POST":
            parameters_dict = parse_post_request(request)
            ner_logger.debug('Start Bulk Detection: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        elif request.method == "GET":
            parameters_dict = get_parameters_dictionary(request)
            ner_logger.debug('Start: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])

        number_detection = NumberDetector(entity_name=parameters_dict[PARAMETER_ENTITY_NAME],
                                          language=parameters_dict[PARAMETER_SOURCE_LANGUAGE],
                                          unit_type=parameters_dict[PARAMETER_NUMBER_UNIT_TYPE])

        if parameters_dict[PARAMETER_MIN_DIGITS] and parameters_dict[PARAMETER_MAX_DIGITS]:
            min_digit = int(parameters_dict[PARAMETER_MIN_DIGITS])
            max_digit = int(parameters_dict[PARAMETER_MAX_DIGITS])
            number_detection.set_min_max_digits(min_digit=min_digit, max_digit=max_digit)

        message = parameters_dict[PARAMETER_MESSAGE]
        entity_output = None

        if isinstance(message, six.string_types):
            entity_output = number_detection.detect(message=message,
                                                    structured_value=parameters_dict[PARAMETER_STRUCTURED_VALUE],
                                                    fallback_value=parameters_dict[PARAMETER_FALLBACK_VALUE],
                                                    bot_message=parameters_dict[PARAMETER_BOT_MESSAGE])
        elif isinstance(message, (list, tuple)):
            entity_output = number_detection.detect_bulk(messages=message)

        ner_logger.debug('Finished %s : %s ' % (parameters_dict[PARAMETER_ENTITY_NAME], entity_output))
    except TypeError as e:
        ner_logger.exception('Exception for numeric: %s ' % e)
        return HttpResponse(status=500)

    return HttpResponse(json.dumps({'data': entity_output}), content_type='application/json')


@csrf_exempt
def number_range(request):
    """Use NumberDetector to detect numerals

        Args:
            request: url parameters:

            request params:
                message (str): natural text on which detection logic is to be run. Note if structured value is
                                       detection is run on structured value instead of message
                entity_name (str): name of the entity. Also acts as elastic-search dictionary name
                                  if entity uses elastic-search lookup
                structured_value (str): Value obtained from any structured elements. Note if structured value is
                                       detection is run on structured value instead of message
                                       (For example, UI elements like form, payload, etc)
                fallback_value (str): If the detection logic fails to detect any value either from structured_value
                                 or message then we return a fallback_value as an output.
                bot_message (str): previous message from a bot/agent.
                unit_type(str): restrict number range to detect for some unit types like 'currency', 'temperature'


       Returns:
           HttpResponse: Response containing dictionary having containing entity_value, original_text and detection;
                         entity_value is in itself a dict with its keys varying from entity to entity

       Examples:
           message = "we expect 200-300 people in room"
           entity_name = 'people_range'
           structured_value = None
           fallback_value = None
           bot_message = None
           unit_type=None
           output = number_range(request)
           print output

           >> [{'detection': 'message', 'original_text': '200-300', 'entity_value': {'min_value': '200',
                'max_value': '300', 'unit': None}}]
       """
    try:
        parameters_dict = {}
        if request.method == "POST":
            parameters_dict = parse_post_request(request)
            ner_logger.debug('Start Bulk Detection: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        elif request.method == "GET":
            parameters_dict = get_parameters_dictionary(request)
            ner_logger.debug('Start: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])

        number_range_detector = NumberRangeDetector(entity_name=parameters_dict[PARAMETER_ENTITY_NAME],
                                                    language=parameters_dict[PARAMETER_SOURCE_LANGUAGE],
                                                    unit_type=parameters_dict[PARAMETER_NUMBER_UNIT_TYPE])

        message = parameters_dict[PARAMETER_MESSAGE]
        entity_output = None

        if isinstance(message, six.string_types):
            entity_output = number_range_detector.detect(message=message,
                                                         structured_value=parameters_dict[PARAMETER_STRUCTURED_VALUE],
                                                         fallback_value=parameters_dict[PARAMETER_FALLBACK_VALUE],
                                                         bot_message=parameters_dict[PARAMETER_BOT_MESSAGE])
        elif isinstance(message, (list, tuple)):
            entity_output = number_range_detector.detect_bulk(messages=message)

        ner_logger.debug('Finished %s : %s ' % (parameters_dict[PARAMETER_ENTITY_NAME], entity_output))

    except TypeError as e:
        ner_logger.exception('Exception for numeric: %s ' % e)
        return HttpResponse(status=500)

    return HttpResponse(json.dumps({'data': entity_output}), content_type='application/json')


@csrf_exempt
def phone_number(request):
    """Uses PhoneDetector to detect phone numbers

        request params:
            message (list or str): string for get request and list of text for bulk call through
                                   post request on which detection logic is to be run
            entity_name (str): name of the entity. Also acts as elastic-search dictionary name
                              if entity uses elastic-search lookup
            structured_value (str): Value obtained from any structured elements. Note if structured value is
                                   detection is run on structured value instead of message
                                   (For example, UI elements like form, payload, etc)
            fallback_value (str): If the detection logic fails to detect any value either from structured_value
                             or message then we return a fallback_value as an output.
            bot_message (str): previous message from a bot/agent.
            source_language (str): language for which the phone numbers have to be detected

        Returns:
            response (django.http.response.HttpResponse): HttpResponse object
        Examples:

        message = "Call 02226129857 and message +1(408) 92-124 and send 100rs to 91 9820334416 9920441344"
        entity_name = 'phone_number'
        structured_value = None
        fallback_value = None
        bot_message = None
        source_language = 'en'

        entity_output:

         [
        {
            "detection": "message",
            "original_text": "91 9820334416",
            "entity_value": {
                "value": "919820334416"
            },
            "language": "en"
        },
        {
            "detection": "message",
            "original_text": "9920441344",
            "entity_value": {
                "value": "9920441344"
            },
            "language": "en"
        },
        {
            "detection": "message",
            "original_text": "02226129857",
            "entity_value": {
                "value": "02226129857"
            },
            "language": "en"
        },
        {
            "detection": "message",
            "original_text": "+1(408) 92-124",
            "entity_value": {
                "value": "140892124"
            },
            "language": "en"
        }
        ]
        message = ["Call 02226129857' , 'message +1(408) 92-124' ,'send 100rs to 91 9820334416 9920441344']
        entity_name = 'phone_number'
        source_language = 'en'

        entity_output:
        [
           [{
                    "detection": "message",
                    "original_text": "02226129857",
                    "entity_value": {
                        "value": "02226129857"
                    },
                    "language": "en"
                }

            ],
            [
                {
                    "detection": "message",
                    "original_text": "+1(408) 92-124",
                    "entity_value": {
                        "value": "140892124"
                    },
                    "language": "en"
                }
            ],
            [
                {
                    "detection": "message",
                    "original_text": "91 9820334416",
                    "entity_value": {
                        "value": "919820334416"
                    },
                    "language": "en"
                },
                {
                    "detection": "message",
                    "original_text": "9920441344",
                    "entity_value": {
                        "value": "9920441344"
                    },
                    "language": "en"
                }

            ]
        ]
        """
    try:
        if request.method == "POST":
            parameters_dict = parse_post_request(request)
            ner_logger.debug('Start Bulk Detection: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        elif request.method == "GET":
            parameters_dict = get_parameters_dictionary(request)
            ner_logger.debug('Start: %s ' % parameters_dict[PARAMETER_ENTITY_NAME])
        entity_name = parameters_dict[PARAMETER_ENTITY_NAME]
        language = parameters_dict[PARAMETER_SOURCE_LANGUAGE]

        ner_logger.debug('Entity Name %s' % entity_name)
        ner_logger.debug('Source Language %s' % language)

        phone_number_detection = PhoneDetector(entity_name=entity_name, language=language)
        message = parameters_dict[PARAMETER_MESSAGE]
        if isinstance(message, six.string_types):
            entity_output = phone_number_detection.detect(message=message,
                                                          structured_value=parameters_dict[PARAMETER_STRUCTURED_VALUE],
                                                          fallback_value=parameters_dict[PARAMETER_FALLBACK_VALUE],
                                                          bot_message=parameters_dict[PARAMETER_BOT_MESSAGE])
        elif isinstance(message, (list, tuple)):
            entity_output = phone_number_detection.detect_bulk(messages=message)
        ner_logger.debug('Finished %s : %s ' % (parameters_dict[PARAMETER_ENTITY_NAME], entity_output))
    except TypeError as e:
        ner_logger.exception('Exception for phone_number: %s ' % e)
        return HttpResponse(status=500)

    return HttpResponse(json.dumps({'data': entity_output}), content_type='application/json')
