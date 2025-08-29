import logging
import time
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.item.ExtensionSmallResultItem import ExtensionSmallResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
import requests
import json

logger = logging.getLogger(__name__)
EXTENSION_ICON = 'images/icon.png'

def wrap_text(text, max_width=50):
    words = text.split()
    lines = []
    current_line = ''
    for word in words:
        if len(current_line + word) <= max_width:
            current_line += ' ' + word
        else:
            lines.append(current_line.strip())
            current_line = word
    lines.append(current_line.strip())
    return '\n'.join(lines)


class GPTExtension(Extension):
    """
    Ulauncher extension to generate text using OpenAI
    """

    def __init__(self):
        super(GPTExtension, self).__init__()
        logger.info('GPT-3 extension started')
        self.session = requests.Session() # Create a session for connection pooling (faster)
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


class KeywordQueryEventListener(EventListener):
    """
    Event listener for KeywordQueryEvent
    """

    def on_event(self, event, extension):
        start_time = time.time()
        logger.debug('Processing user preferences')
        # Get user preferences
        try:
            api_key = extension.preferences['api_key']
            max_tokens = int(extension.preferences['max_completion_tokens'])
            frequency_penalty = float(
                extension.preferences['frequency_penalty'])
            presence_penalty = float(extension.preferences['presence_penalty'])
            temperature = float(extension.preferences['temperature'])
            top_p = float(extension.preferences['top_p'])
            system_prompt = extension.preferences['system_prompt']
            line_wrap = int(extension.preferences['line_wrap'])
            model = extension.preferences['model']
            verbosity = extension.preferences['verbosity']
            reasoning_effort = extension.preferences['reasoning_effort']
            if model == 'custom':
                model = extension.preferences['custom_model']
            endpoint = extension.preferences['endpoint_url']
        # pylint: disable=broad-except
        except Exception as err:
            logger.error('Failed to parse preferences: %s', str(err))
            return RenderResultListAction([
                ExtensionResultItem(icon=EXTENSION_ICON,
                                    name='An error occured',
                                    description=wrap_text('Failed to parse preferences: ' + str(err)),
                                    on_enter=CopyToClipboardAction(str(err)))
            ])

        # Get search term
        search_term = event.get_argument()
        logger.debug('Search query: %s', search_term)
        # Display blank prompt if user hasn't typed anything
        if not search_term:
            logger.debug('Displaying blank prompt')
            return RenderResultListAction([
                ExtensionResultItem(icon=EXTENSION_ICON,
                                    name='Type in a prompt...',
                                    on_enter=DoNothingAction())
            ])

        # Create POST request
        headers = {
            'content-type': 'application/json',
            'Authorization': 'Bearer ' + api_key
        }

        body = {
            "messages": [
                {
                    "role": "developer",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": search_term
                }
            ],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "reasoning_effort": reasoning_effort,
            "verbosity": verbosity,
            "model": model
        }
        body = json.dumps(body)

        logger.debug('Request headers: %s', str(headers))
        logger.debug('Request body: %s', str(body))
        preference_time = time.time() - start_time
        start_time = time.time()
        # Send POST request
        try:
            logger.debug('Sending request')
            response = extension.session.post(endpoint, headers=headers, data=body, timeout=10)
        # pylint: disable=broad-except
        except Exception as err:
            logger.error('Request failed: %s', str(err))
            return RenderResultListAction([
                ExtensionResultItem(icon=EXTENSION_ICON,
                                    name='An error occured',
                                    description=wrap_text('Request failed: ' + str(err)),
                                    on_enter=CopyToClipboardAction(str(err)))
            ])
        request_time = time.time() - start_time
        start_time = time.time()
        logger.debug('Request succeeded')
        logger.debug('Response: %s', response.json())

        # See https://platform.openai.com/docs/api-reference/chat/create for response structure
        try:
            response = response.json()
            answer = response['choices'][0]
        # pylint: disable=broad-except
        except Exception as err:
            logger.error('Failed to parse response: %s', str(response))
            errMsg = "Unknown error, please check logs for more info"
            try:
                errMsg = response['error']['message']
            except Exception:
                pass

            return RenderResultListAction([
                ExtensionResultItem(icon=EXTENSION_ICON,
                                    name='An error occured',
                                    description=wrap_text('Failed to parse response: ' + str(err)),
                                    on_enter=CopyToClipboardAction(str(errMsg)))
            ])

        response_items: list[ExtensionResultItem] = []
        try:
            message = answer['message']['content']
            message = wrap_text(message, line_wrap)

            response_items.append(
                ExtensionSmallResultItem(
                    icon=EXTENSION_ICON,
                    name=message,
                    on_enter=CopyToClipboardAction(message)
                )
            )
            response_items.append(
                ExtensionSmallResultItem(
                    icon=EXTENSION_ICON,
                    name="Open ChatGPT Web",
                    on_enter=OpenUrlAction("https://chatgpt.com/?prompt=" + search_term)
                )
            )
            response_items.append(
                ExtensionSmallResultItem(
                    icon="images/google-logo.png",
                    name="Search on Google",
                    on_enter=OpenUrlAction("https://www.google.com/search?q=" + search_term)
                )
            )
        # pylint: disable=broad-except
        except Exception as err:
            logger.error('Failed to parse response: %s', str(response))
            return RenderResultListAction([
                ExtensionResultItem(icon=EXTENSION_ICON,
                                    name='An error occured',
                                    description=wrap_text('Failed to parse response: ' + str(err)),
                                    on_enter=CopyToClipboardAction(str(err)))
            ])

        try:
            item_string = ' | '.join([item._description for item in response_items])
            logger.debug("Answer: %s", item_string)
        except Exception as err:
            logger.error('Failed to log results: %s', str(err))
            logger.error('Results: %s', str(response_items))

        response_list_time = time.time() - start_time

        logger.debug(f"Preference Loading Time: {preference_time:.2f}s")
        logger.debug(f"Request Execution Time: {request_time:.2f}s")
        logger.debug(f"Response List Creation Time: {response_list_time:.2f}s")

        return RenderResultListAction(response_items)


if __name__ == '__main__':
    GPTExtension().run()
