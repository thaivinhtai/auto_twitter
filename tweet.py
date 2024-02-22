#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto twitter
"""

import concurrent.futures
import asyncio
import sys
from typing import List
import random
import traceback

from json import loads, JSONDecodeError
from os import mkdir, path, listdir, environ
from pathlib import Path
from typing import Union
import time

import argparse

from datetime import datetime

from playwright.async_api import (async_playwright, Page, Browser,
                                  Locator, Playwright, expect,
                                  TimeoutError as PWTimeoutError)


BASE_URL = "https://twitter.com"

CURRENT_DIR = str(Path(__file__).parent.absolute())
AUTH_DIR = f"{CURRENT_DIR}/.auth"
RESULT_DIR = f"{CURRENT_DIR}/result"
MEDIA_FOLDER = f"{CURRENT_DIR}/media"
MEDIA_FILES = [media_file for media_file in listdir(MEDIA_FOLDER)
               if not (media_file.startswith("._")
                       or media_file.endswith(".ai")
                       or media_file.endswith(".psd"))]

CURRENT_TIME = datetime.now().strftime("%H:%M:%S")
UNEXPECTED_ISSUE_FOLDER = f"{RESULT_DIR}/{CURRENT_TIME}-unexpected"
HARD_LOCKED = f"{RESULT_DIR}/{CURRENT_TIME}-hard-locked"
SUSPENDED_DIR = f"{RESULT_DIR}/{CURRENT_TIME}-suspended"
AUTOMATED_DETECTED = f"{RESULT_DIR}/{CURRENT_TIME}-auto-detected"
LIMIT_DIR = f"{RESULT_DIR}/{CURRENT_TIME}-limit"

DEFAULT_SCROLL_TIMES = 10

DEBUG = str(environ.get('AUTO_TWEET_DEBUG')) == "1"


class FailedToUploadMediaException(Exception):
    pass


def __get_args() -> argparse.Namespace:
    """Get arguments.

    Returns
    -------
    argparse.Namespace
        tweet_file : path to tweet content file.
        credential : path to credential file
        headed : run in headed mode
        workers : Max workers to run parallely
    """
    parser = argparse.ArgumentParser(description='Execution arguments')
    parser.add_argument('-t', '--tweet-file',
                        default='contents.txt',
                        help='path to tweet content file.')
    parser.add_argument('-c', '--credential',
                        default='credentials.txt',
                        help='path to credential file')
    parser.add_argument('-d', '--duration',
                        default=50,
                        help='Total time tu run for each thread (seconds)')
    parser.add_argument('--headed', required=False,
                        action="store_true", help='run in headed mode',
                        default=False)
    parser.add_argument('-w', '--workers',
                        required=False, default=4,
                        help="Max workers to run parallely. default = 4")
    return parser.parse_args()


async def wait_for_load(_, page: Page) -> None:
    """

    Parameters
    ----------
    _
    page

    Returns
    -------

    """
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_load_state("load")


def generate_result() -> None:
    """

    Returns
    -------

    """
    if not path.isdir(RESULT_DIR):
        mkdir(RESULT_DIR)

    with open(f'{RESULT_DIR}/result-{CURRENT_TIME}.txt', 'w', encoding='utf8'):
        pass


def get_data_from_file(file_path: str, separator: str = '\n\n') -> List[str]:
    """

    Parameters
    ----------
    file_path
    separator

    Returns
    -------

    """
    with open(file_path, encoding='utf8') as file:
        result = file.read().split(separator)
    return [element for element in result if element != '']


def get_credentials(file_path: str) -> List[List[str]]:
    """

    Parameters
    ----------
    file_path

    Returns
    -------

    """
    result = []
    for cred in get_data_from_file(file_path, separator='\n'):
        if cred.startswith('#'):
            continue
        temp_cred = cred.split(':')
        result.append([element for element in temp_cred if element != ''])
    return result


async def check_expired_or_not(storage_file: str) -> bool:
    """Check expired or not.

    Check if token expired or not.

    Parameters
    ----------
    storage_file : str
        Path to storage file.

    Returns
    -------
    bool
        True - Token is still valid
        False - Need to log in again
    """
    if not path.isfile(storage_file):
        return False
    with open(storage_file, encoding='utf8') as file:
        file_content = file.read()
    try:
        storage = loads(file_content)
    except JSONDecodeError:
        return False
    expired_time = 0
    for item in storage.get("cookies"):
        if item.get("name") == "guest_id":
            expired_time = item.get("expires")
            break
    if expired_time > time.time():
        return True
    return False


async def log_in(page: Page, username: str, password: str) -> None:
    """Log in.

     Log in Twitter.com using username and password

    Parameters
    ----------
    page : playwright.async_api.Page
    username : str
    password

    Returns
    -------

    """
    await page.goto(BASE_URL + "/login")
    await page.fill('input[type="text"]', username)
    await page.keyboard.press('Enter')
    await page.fill('input[type="password"]', password)
    await page.keyboard.press('Enter')


async def attach_media(page: Page, username: str, try_times: int = 0) -> bool:
    """

    Parameters
    ----------
    page
    username
    try_times

    Returns
    -------

    """
    if try_times > 3:
        await page.screenshot(
            path=f"{UNEXPECTED_ISSUE_FOLDER}"
                 f"/{username}-cant-upload-media-{time.time()}.png")
        return False
    file_to_upload = random.choice(MEDIA_FILES)
    async with page.expect_file_chooser(timeout=10000) as fc_info:
        await page.get_by_role(
            "button", name="Add photos or video"
        ).click(timeout=10000)
    file_chooser = await fc_info.value
    await file_chooser.set_files(f"{MEDIA_FOLDER}/{file_to_upload}")
    try:
        if not file_to_upload.endswith("mp4"):
            await expect(
                page.get_by_text("Add description")
            ).to_be_visible(timeout=3000)
            await expect(
                page.get_by_text("Tag people")).to_be_visible(timeout=3000)
        if file_to_upload.endswith("mp4"):
            await expect(
                page.get_by_text("Uploading")).to_be_visible(timeout=3000)
            await page.get_by_text("Uploaded (100%)").click(timeout=1000000)
        if await page.get_by_text(
                "Some of your media failed to upload."
        ).is_visible() or await page.get_by_text("Error").is_visible():
            await wait_for_load(
                await page.get_by_role(
                    "button", name="Remove media").click(), page)
            raise FailedToUploadMediaException("Failed to upload media.")
            # Some of your media failed to load.
    except (PWTimeoutError, AssertionError, FailedToUploadMediaException) as e:
        if DEBUG:
            print(e)
            traceback.print_exc()
        try_times += 1
        print(f"Failed to upload: {file_to_upload}")
        print(f"Try uploading other media ({try_times})")
        await wait_for_load(await page.get_by_role(
            "textbox", name="Post text").click(), page)
        return await attach_media(page, username, try_times)
    return True


async def click_on_location(locator: Locator, page: Page) -> None:
    """

    Parameters
    ----------
    locator
    page

    Returns
    -------

    """
    locator_anchor = await locator.bounding_box()
    await page.mouse.click(locator_anchor['x'] + locator_anchor['width'] / 2,
                           locator_anchor['y'] + locator_anchor['height'] / 2)


async def close_tweet_dialog(page: Page) -> None:
    """

    Parameters
    ----------
    page

    Returns
    -------

    """
    await wait_for_load(
        await page.get_by_test_id("app-bar-close").click(), page)
    await expect(
        page.get_by_test_id("confirmationSheetCancel")).to_be_visible()
    if page.get_by_test_id("confirmationSheetConfirm").is_visible():
        await wait_for_load(
            page.get_by_test_id("confirmationSheetConfirm").click(), page
        )
    else:
        await wait_for_load(
            await page.get_by_test_id("confirmationSheetCancel").click(), page)


async def tweet(page: Page, tweets: List[str], username: str) -> (bool, str):
    """

    Parameters
    ----------
    page
    tweets
    username

    Returns
    -------

    """
    if len(tweets) == 0:
        await close_tweet_dialog(page)
        return False, ""

    new_tweets = list(tweets)
    this_tweet = random.choice(new_tweets)

    if not await attach_media(page, username):
        await close_tweet_dialog(page)
        return False, ""

    tweet_times = 0
    while (await page.get_by_test_id(
            "tweetTextarea_0_label"
    ).get_by_text("Post your reply").is_visible()
           and tweet_times < 5):
        await wait_for_load(await page.get_by_role(
            "textbox", name="Post text").clear(), page)
        await wait_for_load(await page.get_by_role(
            "textbox", name="Post text").click(), page)
        await page.keyboard.press('a')
        await page.keyboard.press('Backspace')
        await wait_for_load(await page.get_by_role(
            "textbox", name="Post text").fill(this_tweet), page)
        await page.keyboard.press("ArrowRight")
        await page.keyboard.press("Enter")
        tweet_times += 1
    if await page.get_by_test_id(
            "tweetTextarea_0_label"
    ).get_by_text("Post your reply").is_visible():
        await page.screenshot(
            path=f"{UNEXPECTED_ISSUE_FOLDER}"
                 f"/{username}-cant-fill-comment-{time.time()}.png")
        await close_tweet_dialog(page)
        return False, ""

    async with page.expect_response(
            lambda response1: "/CreateTweet" in response1.url
                              and response1.status == 200) as response_info:
        if await page.get_by_test_id("tweetButton").is_visible():
            if await page.get_by_test_id("tweetButton").is_enabled():

                await page.get_by_test_id("tweetButton").click(timeout=5000)

                if await page.get_by_text(
                        "Some of your media failed to upload."
                ).is_visible() or await page.get_by_text("Error").is_visible():
                    return False, "suspended or locked"

                if await page.get_by_text(
                        "You are over the daily limit for sending posts."
                ).is_visible():
                    return False, "reach limit"

                if await page.get_by_text(
                        "Whoops! You already said that.").is_visible():
                    await page.get_by_role(
                        "textbox", name="Post text"
                    ).clear()
                    new_tweets.remove(this_tweet)
                    return await tweet(page, new_tweets, username)
            else:
                return False, ""

        data = await (await response_info.value).json()
        post_id = \
            data['data']['create_tweet']['tweet_results']['result']['rest_id']
        with open(
                f'{RESULT_DIR}/result-{CURRENT_TIME}.txt', 'a', encoding='utf8'
        ) as result:
            print(f'https://twitter.com/{username}/status/{post_id}')
            result.write(
                f'https://twitter.com/{username}/status/{post_id}\n'
            )

    return True, ""


async def get_page(username: str, password: str,
                   headed: bool, common_page_options: dict,
                   p: Playwright) -> (Page, Browser, bool, str):
    """

    Parameters
    ----------
    username
    password
    headed
    common_page_options
    p

    Returns
    -------

    """
    browser = await p.chromium.launch(
        headless=headed, slow_mo=1000, timeout=2147483647, channel='chrome',
        args=[
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    storage_state_file = f"{AUTH_DIR}/{username}.json"
    if await check_expired_or_not(storage_state_file):
        context = await browser.new_context(
            storage_state=storage_state_file, **common_page_options
        )
        page = await context.new_page()
        await page.goto(BASE_URL)
    else:
        context = await browser.new_context(**common_page_options)
        page = await context.new_page()
        await log_in(page, username=username, password=password)
    await wait_for_load(None, page)
    try:
        await page.get_by_text("Accept all cookies").click()
    except Exception as e:
        if DEBUG:
            print(username, e)
            traceback.print_exc()
    try:
        await page.wait_for_url("https://twitter.com/home", timeout=5000)
    except PWTimeoutError:
        pass
    can_continue = True
    if page.url not in ("https://twitter.com/home",
                        "https://twitter.com/account/access"):
        can_continue = False
        await login_issue(page=page, username=username, password=password)
    suspended = await check_suspended(
        page=page, username=username, password=password)
    can_continue = can_continue and not suspended
    return browser, page, can_continue, storage_state_file


async def check_suspended(page: Page, username: str,
                          password: str = "") -> bool:
    """

    Parameters
    ----------
    page
    username
    password

    Returns
    -------

    """
    if await page.get_by_text("Your account is suspended").is_visible():
        print(f"{username} is suspended")
        if not path.isdir(SUSPENDED_DIR):
            mkdir(SUSPENDED_DIR)
        await page.screenshot(
            path=f"{SUSPENDED_DIR}/{username}.png")
        with open(
                f"{SUSPENDED_DIR}/accounts.txt",
                "a", encoding='utf8'
        ) as locked:
            if password:
                locked.write(f"{username}:{password}\n")
            else:
                locked.write(f"{username}:{password}\n")
        return True
    return False


async def check_limit(page: Page, username: str, password: str) -> None:
    """

    Parameters
    ----------
    page
    username
    password

    Returns
    -------

    """
    print(f"{username} reaches daily limit")
    if not path.isdir(LIMIT_DIR):
        mkdir(LIMIT_DIR)
    await page.screenshot(
        path=f"{LIMIT_DIR}/{username}.png")
    with open(
            f"{LIMIT_DIR}/accounts.txt",
            "a", encoding='utf8'
    ) as locked:
        locked.write(f"{username}:{password}\n")


async def login_issue(page: Page, username: str, password: str) -> None:
    """

    Parameters
    ----------
    page
    username
    password

    Returns
    -------

    """
    print(f"{username}: Can't not login")
    if not path.isdir(f'{RESULT_DIR}/{CURRENT_TIME}-login-issue'):
        mkdir(f'{RESULT_DIR}/{CURRENT_TIME}-login-issue')
    await page.screenshot(
        path=f"{RESULT_DIR}/{CURRENT_TIME}-login-issue/{username}.png")
    with open(
            f"{RESULT_DIR}/{CURRENT_TIME}-login-issue/accounts.txt",
            "a", encoding='utf8'
    ) as locked:
        locked.write(f"{username}:{password}\n")


async def check_locked(page: Page, username: str, password: str = "") -> bool:
    """

    Parameters
    ----------
    page
    username
    password

    Returns
    -------

    """
    # await page.get_by_text(
    #     "Hmm...this page doesn't exist. Try searching for something else."
    # ).wait_for(state="visible")
    await wait_for_load(await page.reload(), page)
    if page.url == "https://twitter.com/account/access":
        await page.reload()
        if not path.isdir(f'{RESULT_DIR}/{CURRENT_TIME}-locked'):
            mkdir(f'{RESULT_DIR}/{CURRENT_TIME}-locked')
        if await page.get_by_text(
                "Your account has been locked.").is_visible():
            await page.screenshot(
                path=f"{RESULT_DIR}/{CURRENT_TIME}-locked/{username}.png")
            with open(
                    f"{RESULT_DIR}/{CURRENT_TIME}-locked/locked_accounts.txt",
                    "a", encoding='utf8'
            ) as locked:
                if password:
                    locked.write(f"{username}:{password}\n")
                else:
                    locked.write(f"{username}\n")
            return True
    return False


async def check_hard_locked(page: Page, username: str) -> bool:
    """

    Parameters
    ----------
    page
    username

    Returns
    -------

    """
    if await page.get_by_text("Unlock the ability to post").is_visible():
        print(f"{username} is hard locked")
        if not path.isdir(HARD_LOCKED):
            mkdir(HARD_LOCKED)
        await page.screenshot(
            path=f"{HARD_LOCKED}/{username}-hard-locked.png")
        with open(
                f"{HARD_LOCKED}/hard_locked_accounts.txt",
                "a", encoding='utf8'
        ) as locked:
            locked.write(f"{username}\n")
        return True
    return False


async def browse_an_article(like: Locator, username: str,
                            page: Page, tweets: List[str]) -> bool:
    """

    Parameters
    ----------
    like
    username
    page
    tweets

    Returns
    -------

    """
    group_action = like.locator("../..")
    article = group_action.locator("../../../../../../..")
    reply_btn = group_action.get_by_test_id('reply')
    try:
        await reply_btn.click(timeout=5000)
    except PWTimeoutError:
        await click_on_location(reply_btn, page)
        if DEBUG:
            print(username)
            traceback.print_exc()
    if not await page.get_by_role(
            "textbox", name="Post text").is_visible():
        await article.screenshot(
            path=f"{UNEXPECTED_ISSUE_FOLDER}"
                 f"/{username}-not-reply-{time.time()}.png")
        return False
    status_code, message = await tweet(page, tweets, username)
    if not status_code:
        if message == "suspended or locked":
            await wait_for_load(
                await page.goto("https://twitter.com/home"), page
            )
            if (await check_suspended(page=page, username=username)
                    or await check_locked(page=page, username=username)):
                sys.exit()
        return False

    if await check_hard_locked(page, username):
        sys.exit()

    if await page.get_by_text(
            "This request looks like it might be automated.").is_visible():
        await page.screenshot(
            path=f"{AUTOMATED_DETECTED}"
                 f"/{username}-{time.time()}.png")
        sys.exit()

    while await page.get_by_text("Your post was sent.").is_visible():
        time.sleep(1)

    try:
        await like.click(timeout=5000)
    except PWTimeoutError:
        if DEBUG:
            print(username)
            traceback.print_exc()
        await article.screenshot(
            path=f"{UNEXPECTED_ISSUE_FOLDER}"
                 f"/{username}-not-like-{time.time()}.png")
    return True


async def browse_articles(likes: List[Locator], username: str,
                          page: Page, tweets: List[str]
                          ) -> List[Union[Locator, str]]:
    """

    Parameters
    ----------
    likes
    username
    page
    tweets

    Returns
    -------

    """
    for like in likes:
        if await browse_an_article(like=like, username=username,
                                   page=page, tweets=tweets):
            wait_time = random.choice((3, 5, 6, 7, 8, 9))
            time.sleep(wait_time)
    scroll = 0
    likes = await page.get_by_test_id('like').all()
    while scroll < DEFAULT_SCROLL_TIMES and len(likes) == 0:
        await wait_for_load(await page.keyboard.press('PageDown'), page)
        scroll += 1
        likes = await page.get_by_test_id('like').all()
    return likes


async def get_likes_when_first_loading(page: Page) -> List[Locator]:
    scroll = 0
    likes = await page.get_by_test_id('like').all()
    while len(likes) == 0 and scroll < DEFAULT_SCROLL_TIMES:
        await wait_for_load(
            await page.keyboard.press('PageDown'), page
        )
        scroll += 1
        likes = await page.get_by_test_id('like').all()
    return likes


async def like_and_tweet(username: str, password: str,
                         tweets: list, headed: bool) -> None:
    """

    Parameters
    ----------
    username
    password
    tweets
    headed

    Returns
    -------

    """
    common_page_options = {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/119.0.0.0 Safari/537.36",
        "viewport": {
            'width': 1980, 'height': 1080
        }
    }
    if DEBUG:
        common_page_options["record_video_dir"] = "./result"
    async with async_playwright() as p:
        browser, page, can_continue, storage_state_file = await get_page(
            username=username, password=password, headed=headed,
            common_page_options=common_page_options, p=p
        )
        if not can_continue:
            return
        if await check_locked(page, username=username, password=password):
            return
        followings = get_data_from_file('./followings.txt')
        print(followings)
        random.shuffle(followings)
        # main_follow = followings[0]
        # others = list(followings[1:])
        # random.shuffle(others)
        # followings = [main_follow, *others]
        for following in followings:
            try:
                if DEBUG:
                    print(following)

                await wait_for_load(await page.goto(following), page)
                likes = await get_likes_when_first_loading(page)

                while len(likes) > 0:
                    likes = await browse_articles(
                        likes=likes, username=username,
                        page=page, tweets=tweets
                    )
            except (PWTimeoutError, AssertionError):
                print(username)
                print(following)
                await page.screenshot(
                    path=f"{UNEXPECTED_ISSUE_FOLDER}"
                         f"/{username}-{time.time()}.png")
                traceback.print_exc()
                continue

        if not path.exists(AUTH_DIR):
            mkdir(AUTH_DIR)
        await page.context.storage_state(path=storage_state_file)
        await browser.close()


def run(username: str, password: str, tweets: list, headed: bool) -> None:
    """

    Parameters
    ----------
    username
    password
    tweets
    headed

    Returns
    -------

    """
    asyncio.run(like_and_tweet(username=username, password=password,
                               tweets=tweets, headed=headed))


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    arg = __get_args()
    credentials = get_credentials(arg.credential)
    contents = get_data_from_file(arg.tweet_file)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=int(arg.workers))
    generate_result()
    # results = {}
    for credential in credentials:
        pool.submit(
            run, credential[0], credential[1], contents, arg.headed is not True
        )
    # for user in results:
    #     print(f"{user}: {results[user].result()}")

    pool.shutdown(wait=True)
    print("finish")
    # You are over the daily limit for sending posts.