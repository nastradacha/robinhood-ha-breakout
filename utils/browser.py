# ✅ Chrome driver pin & prompt rules verified – 2025-08-06

"""Robinhood Browser Automation Module

Provides sophisticated browser automation for Robinhood options trading with anti-detection
measures and robust error handling. This module handles all browser interactions including
login, navigation, option selection, and trade setup.

Key Features:
- Undetected Chrome browser with stealth mode
- Robust login with MFA support
- Automatic cookie management and session persistence
- ATM option finding and selection
- Trade setup automation (stops at Review screen)
- Idle session management and recovery
- Comprehensive error handling and logging

Safety Measures:
- Never auto-submits trades
- Always stops at Robinhood Review screen
- Requires manual user confirmation
- Session recovery for interrupted workflows
- Extensive logging for debugging

Anti-Detection Features:
- Undetected ChromeDriver to bypass bot detection
- Human-like typing patterns
- Random delays and mouse movements
- Stealth mode configuration
- Session cookie reuse

Usage:
    # Context manager (recommended)
    with RobinhoodBot() as bot:
        bot.login(username, password)
        bot.navigate_to_options('SPY')
        option_data = bot.find_atm_option(current_price, 'CALL')
        bot.click_option_and_buy(option_data, quantity=1)

    # Manual management
    bot = RobinhoodBot(headless=False)
    bot.start_browser()
    # ... trading operations ...
    bot.close()

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import time as time_module
import logging
import re
import tempfile
import shutil
from typing import Optional, Dict
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
import undetected_chromedriver as uc
from pathlib import Path
from utils.llm import load_config

# Try to import stealth, fallback if not available
try:
    from undetected_chromedriver.stealth import stealth

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    stealth = None

logger = logging.getLogger(__name__)


class RobinhoodBot:
    """
    Sophisticated browser automation bot for Robinhood options trading.

    This class provides comprehensive browser automation capabilities for interacting
    with Robinhood's web interface. It handles login, navigation, option selection,
    and trade setup while implementing anti-detection measures and robust error handling.

    Key Capabilities:
    - Secure login with MFA support
    - Session cookie management and persistence
    - ATM option discovery and selection
    - Trade setup automation (stops at Review screen)
    - Idle session recovery and management
    - Human-like interaction patterns

    Anti-Detection Features:
    - Undetected ChromeDriver to bypass bot detection
    - Stealth mode configuration
    - Human-like typing with random delays
    - Session cookie reuse to avoid repeated logins
    - Random mouse movements and realistic timing

    Safety Guarantees:
    - NEVER auto-submits trades
    - Always stops at Robinhood Review screen
    - Requires explicit manual confirmation
    - Comprehensive logging for audit trails
    - Graceful error handling and recovery

    Attributes:
        driver (WebDriver): Selenium WebDriver instance
        headless (bool): Whether to run browser in headless mode
        implicit_wait (int): Default wait time for element discovery
        page_load_timeout (int): Maximum time to wait for page loads
        wait (WebDriverWait): Explicit wait instance for complex conditions
        idle_since (datetime): Timestamp of last activity for idle management
        last_symbol (str): Last traded symbol for session optimization

    Example:
        >>> with RobinhoodBot(headless=False) as bot:
        ...     bot.login('username', 'password')
        ...     bot.navigate_to_options('SPY')
        ...     option = bot.find_atm_option(635.0, 'CALL')
        ...     bot.click_option_and_buy(option, quantity=1)
        ...     # User manually reviews and confirms on Robinhood
    """

    def __init__(
        self,
        headless: bool = False,
        implicit_wait: int = 10,
        page_load_timeout: int = 30,
    ):
        """
        Initialize the RobinhoodBot with browser configuration.

        Args:
            headless (bool): Run browser in headless mode (default: False)
                           Note: Headless mode may trigger bot detection
            implicit_wait (int): Default wait time for elements (default: 10 seconds)
            page_load_timeout (int): Max page load wait time (default: 30 seconds)

        Note:
            Browser is not started until start_browser() is called or when
            used as a context manager.
        """
        self.driver = None
        self.headless = headless
        self.implicit_wait = implicit_wait
        self.page_load_timeout = page_load_timeout
        self.wait = None
        self.idle_since = None
        self.last_symbol = None
        self.last_action = time_module.time()  # Track last action for session management
        self._temp_profile_dir = None  # Track temp profile for cleanup

    def __enter__(self):
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

    def start_browser(self):
        """Launch Chrome with robust startup and cleanup."""
        import psutil

        # Kill any existing Chrome processes that might be interfering
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if "chrome" in proc.info["name"].lower():
                    try:
                        proc.terminate()
                    except:
                        pass
            logger.info("Cleaned up existing Chrome processes")
        except Exception as e:
            logger.warning(f"Could not clean Chrome processes: {e}")

        # Load configuration for Chrome version with fallback
        try:
            config = load_config()
            chrome_major = config.get("CHROME_MAJOR")
            if chrome_major is None:
                chrome_major = None
                logger.info("Chrome version auto-detection enabled")
            else:
                logger.info(f"Using pinned Chrome version: {chrome_major}")
        except Exception as e:
            logger.warning(f"Could not load config, using auto-detection: {e}")
            chrome_major = None

        # Enhanced Chrome detection and fallback
        import subprocess
        try:
            # Try to detect actual Chrome version on system
            result = subprocess.run(
                ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                actual_version = result.stdout.split()[-1].split('.')[0]
                logger.info(f"Detected Chrome version: {actual_version}")
                if chrome_major and str(chrome_major) != actual_version:
                    logger.warning(f"Config version {chrome_major} != detected {actual_version}, using detected")
                    chrome_major = int(actual_version)
        except Exception as e:
            logger.info(f"Chrome version detection failed: {e}")

        # Enhanced startup strategies with better error handling
        strategies = [
            {"name": "Auto-detect Clean", "use_profile": False, "minimal": True, "version": None},
            {"name": "Pinned Version Clean", "use_profile": False, "minimal": True, "version": chrome_major},
            {"name": "Auto-detect with Profile", "use_profile": True, "minimal": True, "version": None},
            {"name": "Pinned with Profile", "use_profile": True, "minimal": True, "version": chrome_major},
            {"name": "Fallback Minimal", "use_profile": False, "minimal": True, "version": None, "no_sandbox": True},
        ]

        for i, strategy in enumerate(strategies):
            try:
                logger.info(f"Attempt {i+1}: {strategy['name']}")
                options = uc.ChromeOptions()

                if strategy["use_profile"]:
                    # Use truly random temporary profile
                    self._temp_profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")
                    options.add_argument(f"--user-data-dir={self._temp_profile_dir}")
                    logger.info(f"Created temp profile: {self._temp_profile_dir}")

                # Enhanced stability options
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-background-networking")
                options.add_argument("--disable-features=ChromeCleanup,LoadCryptoTokenExtension,VizDisplayCompositor")
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-plugins")
                options.add_argument("--disable-images")
                options.add_argument("--disable-javascript")

                # Port management - use random port to avoid conflicts
                import random
                debug_port = random.randint(9000, 9999)
                options.add_argument(f"--remote-debugging-port={debug_port}")

                # Additional stability flags for problematic systems
                if strategy.get("no_sandbox"):
                    options.add_argument("--disable-web-security")
                    options.add_argument("--disable-features=VizDisplayCompositor")
                    options.add_argument("--single-process")

                if self.headless:
                    options.add_argument("--headless=new")
                    options.add_argument("--disable-software-rasterizer")

                # Launch Chrome with version strategy
                driver_kwargs = {"options": options}
                strategy_version = strategy.get("version")
                if strategy_version:
                    driver_kwargs["version_main"] = strategy_version
                    logger.info(f"Using Chrome version: {strategy_version}")
                else:
                    logger.info("Using Chrome auto-detection")

                # Add timeout and retry logic
                self.driver = uc.Chrome(**driver_kwargs)

                # Test driver responsiveness
                self.driver.set_page_load_timeout(10)
                self.driver.implicitly_wait(self.implicit_wait)
                self.wait = WebDriverWait(self.driver, 10)

                # Quick connectivity test
                self.driver.get("data:text/html,<html><body>Chrome Test</body></html>")

                logger.info(f"[OK] Chrome started successfully with {strategy['name']}")
                break

            except Exception as e:
                logger.warning(f"❌ {strategy['name']} failed: {str(e)[:100]}...")

                # Cleanup failed driver
                try:
                    if hasattr(self, "driver") and self.driver:
                        self.driver.quit()
                        self.driver = None
                except:
                    pass

                # Enhanced temp profile cleanup with retry logic
                if self._temp_profile_dir and Path(self._temp_profile_dir).exists():
                    try:
                        # Force close any file handles first
                        import gc
                        gc.collect()
                        time_module.sleep(0.5)
                        
                        # Try multiple cleanup attempts
                        for attempt in range(3):
                            try:
                                shutil.rmtree(self._temp_profile_dir)
                                self._temp_profile_dir = None
                                logger.info(f"Temp profile cleaned up on attempt {attempt + 1}")
                                break
                            except (OSError, PermissionError) as e:
                                if attempt < 2:
                                    logger.info(f"Cleanup attempt {attempt + 1} failed, retrying...")
                                    time_module.sleep(1)
                                else:
                                    logger.warning(f"Could not cleanup temp profile after 3 attempts: {e}")
                                    # Mark for later cleanup
                                    self._temp_profile_dir = None
                    except Exception as cleanup_error:
                        logger.warning(f"Temp profile cleanup error: {cleanup_error}")

                if i == len(strategies) - 1:
                    logger.error("All Chrome startup strategies failed")
                    raise Exception(
                        f"Could not start Chrome after {len(strategies)} attempts"
                    )

                # Wait before next attempt
                time_module.sleep(2)

        # Apply stealth if available
        if STEALTH_AVAILABLE and stealth:
            stealth(
                self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL",
                fix_hairline=True,
            )
            logger.info("Applied stealth configuration")
        else:
            logger.warning(
                "Stealth module not available, using basic undetected-chromedriver"
            )

        # 👉 Maximize browser window for better visibility
        self.driver.maximize_window()

        # Load cookies if available
        cookie_path = Path("robin_cookies_selenium.json")
        if cookie_path.exists():
            try:
                import json

                self.driver.get("https://robinhood.com")  # domain must be loaded first
                bad = []
                with cookie_path.open(encoding="utf-8") as fh:
                    for ck in json.load(fh):
                        try:
                            # strip SameSite=None unless secure:true
                            if ck.get("sameSite") == "None" and not ck.get(
                                "secure", False
                            ):
                                ck.pop("sameSite", None)
                            # delete Max-Age or Expires strings Selenium can't parse
                            for k in ("expiry", "expires"):
                                if k in ck and isinstance(ck[k], str):
                                    ck.pop(k)
                            self.driver.add_cookie(ck)
                        except Exception as err:
                            bad.append((ck.get("name"), str(err)))
                if bad:
                    logger.warning(
                        f"Skipped {len(bad)} cookies: {[n for n,_ in bad][:4]}…"
                    )
                else:
                    logger.info("Injected saved Robinhood session cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")

        logger.info("Browser started successfully (stealth mode)")
        self.last_action = time_module.time()  # Update last action timestamp

    def ensure_session(self, max_idle_sec: int = 900) -> bool:
        """
        Ensure browser session is active and restart if idle too long.

        Args:
            max_idle_sec: Maximum idle time in seconds (default 900 = 15 minutes)

        Returns:
            True if session is active, False if restart failed
        """
        try:
            current_time = time_module.time()
            idle_time = current_time - self.last_action

            if idle_time > max_idle_sec:
                logger.info(
                    f"[SESSION] Idle for {idle_time:.0f}s (>{max_idle_sec}s), restarting browser"
                )
                return self.restart()

            # Check if browser is still responsive
            if self.driver is None:
                logger.info("[SESSION] No active driver, starting browser")
                self.start_browser()
                return True

            try:
                # Simple responsiveness check
                self.driver.current_url
                self.last_action = current_time
                return True
            except Exception as e:
                logger.warning(f"[SESSION] Browser unresponsive: {e}, restarting")
                return self.restart()

        except Exception as e:
            logger.error(f"[SESSION] Error ensuring session: {e}")
            return False

    def restart(self) -> bool:
        """
        Restart the browser session.

        Returns:
            True if restart successful, False otherwise
        """
        try:
            logger.info("[SESSION] Restarting browser session")

            # Close existing session
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
                self.wait = None

            # Start new session
            self.start_browser()
            self.last_action = time_module.time()

            logger.info("[SESSION] Browser session restarted successfully")
            return True

        except Exception as e:
            logger.error(f"[SESSION] Failed to restart browser: {e}")
            return False

    def _update_last_action(self):
        """Update the last action timestamp."""
        self.last_action = time_module.time()

    def ensure_open(self, symbol: str) -> bool:
        """Ensure the options chain is open for the given symbol.

        Re-opens the options chain if the session has timed out or if we're
        on a different symbol.

        Args:
            symbol: Stock symbol (e.g., 'SPY')

        Returns:
            True if options chain is accessible, False otherwise
        """
        try:
            # Check if we need to navigate to options
            current_url = self.driver.current_url

            # If we're not on an options page or it's a different symbol
            if (
                "/options/" not in current_url
                or self.last_symbol != symbol
                or "login" in current_url.lower()
            ):

                logger.info(f"[ENSURE_OPEN] Navigating to {symbol} options chain")
                if self.navigate_to_options(symbol):
                    self.last_symbol = symbol
                    return True
                else:
                    return False

            # Test if the page is still responsive
            try:
                # Try to find any options-related element to verify page is loaded
                self.driver.find_element(
                    By.CSS_SELECTOR,
                    "[data-testid*='option'], button[data-testid*='ask'], button[data-testid*='bid']",
                )
                logger.debug(f"[ENSURE_OPEN] {symbol} options chain is accessible")
                return True
            except:
                # Page might be stale, try to refresh
                logger.info(
                    f"[ENSURE_OPEN] Options page seems stale, refreshing {symbol}"
                )
                if self.navigate_to_options(symbol):
                    self.last_symbol = symbol
                    return True
                else:
                    return False

        except Exception as e:
            logger.error(f"[ENSURE_OPEN] Error ensuring options page: {e}")
            return False

    def _human_type(self, element, text, min_delay=0.06, max_delay=0.15):
        """Send keys with human-like pauses."""
        import random

        for ch in text:
            element.send_keys(ch)
            time_module.sleep(random.uniform(min_delay, max_delay))

    def login(self, username: str, password: str) -> bool:
        """
        Log in to Robinhood with manual MFA handling.

        Args:
            username: Robinhood username/email
            password: Robinhood password

        Returns:
            True if login successful
        """
        try:
            logger.info("Navigating to Robinhood login page")
            self.driver.get("https://robinhood.com/login")
            time_module.sleep(3)

            # Find and fill username
            username_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_field.clear()
            self._human_type(username_field, username)
            time_module.sleep(2)

            # Find and fill password
            password_field = self.driver.find_element(By.NAME, "password")
            password_field.clear()
            self._human_type(password_field, password)
            time_module.sleep(2)

            # Click login button
            login_button = self.driver.find_element(
                By.CSS_SELECTOR, "button[type='submit']"
            )
            login_button.click()

            logger.info("Credentials submitted, waiting for MFA...")

            # Wait for MFA completion - look for dashboard or portfolio elements
            print("[MFA] Please complete MFA on your phone or via SMS.")

            # Wait for successful login (look for dashboard elements)
            try:
                # Wait up to 120 seconds for MFA completion
                WebDriverWait(self.driver, 120).until(
                    lambda driver: driver.find_elements(
                        By.CSS_SELECTOR, "a[href='/account']"
                    )
                )
                logger.info("[OK] Login successful!")

                # Save a fresh cookie jar once login is confirmed
                import json

                saved = [
                    ck
                    for ck in self.driver.get_cookies()
                    if ck["domain"].endswith("robinhood.com")
                ]
                Path("robin_cookies_selenium.json").write_text(
                    json.dumps(saved, indent=2)
                )
                logger.info("Saved fresh Robinhood cookies for next session")

                return True

            except TimeoutException:
                logger.error("MFA timeout - login failed")
                return False

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def navigate_to_options(self, symbol: str = "SPY") -> bool:
        """
        Navigate to the options chain for a given symbol.

        Args:
            symbol: Stock symbol (default: SPY)

        Returns:
            True if navigation successful
        """
        # Using time_module (imported at top of file)
        try:
            options_url = f"https://robinhood.com/options/chains/{symbol}"
            logger.info(f"Navigating to {symbol} options chain")

            self.driver.get(options_url)
            time_module.sleep(5)

            # Wait for options chain to load
            self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-testid='OptionChainOptionTypeControl']")
                )
            )

            logger.info(f"Successfully loaded {symbol} options chain")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to options: {e}")
            return False

    def navigate_to_symbol(self, symbol: str) -> bool:
        """
        Navigate to a symbol's options page.
        
        Args:
            symbol: Stock symbol to navigate to
            
        Returns:
            True if navigation successful
        """
        return self.navigate_to_options(symbol)

    def select_option_type(self, option_type: str, timeout: int = 10) -> bool:
        """
        Click the "Call" or "Put" toggle in the Robinhood options chain.
        Based on actual DOM structure from Robinhood interface.

        Args:
            option_type: "CALL" or "PUT"
            timeout: max seconds to wait for element

        Returns:
            True if clicked successfully, False otherwise
        """
        target_text = "Call" if option_type.upper() == "CALL" else "Put"

        try:
            # Wait for the option type control to be present
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-testid='OptionChainOptionTypeControl']")
                )
            )

            # Strategy 1: Look for button with exact text within the control
            try:
                button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            f"//div[@data-testid='OptionChainOptionTypeControl']//button[normalize-space()='{target_text}']",
                        )
                    )
                )
                button.click()
                logger.info(
                    f"Selected {target_text} via OptionChainOptionTypeControl XPath"
                )
                time_module.sleep(1)
                return True
            except TimeoutException:
                pass

            # Strategy 2: Look for any button with the target text
            try:
                button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            f"//button[normalize-space()='{target_text}' or .//span[normalize-space()='{target_text}']]",
                        )
                    )
                )
                button.click()
                logger.info(f"Selected {target_text} via general button XPath")
                time_module.sleep(2)
                return True
            except TimeoutException:
                pass

            # Strategy 3: JavaScript fallback to find and click button
            try:
                result = self.driver.execute_script(
                    """
                    // Look for buttons containing the target text
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const targetButton = buttons.find(btn => 
                        btn.textContent.trim() === arguments[0] ||
                        btn.innerText.trim() === arguments[0]
                    );
                    
                    if (targetButton) {
                        targetButton.click();
                        return true;
                    }
                    return false;
                    """,
                    target_text,
                )

                if result:
                    logger.info(f"Selected {target_text} via JavaScript fallback")
                    time_module.sleep(2)
                    return True
            except Exception as js_error:
                logger.warning(f"JavaScript fallback failed: {js_error}")

            logger.warning(f"Could not find {target_text} button in options chain")
            return False

        except Exception as e:
            logger.error(f"Failed to select option type {option_type}: {e}")
            return False

    def find_atm_option(self, current_price: float, option_type: str) -> Optional[Dict]:
        """
        Returns {"strike": float, "element": WebElement} for the ATM CALL/PUT row.
        Accepts the live `current_price` and side string ("CALL"/"PUT").
        Tries both ChainTableRow-* <div> layout and <tr role='row'> layout.
        """
        # Using time_module (imported at top of file)

        # 1) Ensure correct side is active
        if not self.select_option_type(option_type):
            logger.error(f"Failed to click {option_type} toggle")
            return None
        time_module.sleep(1)  # let table paint

        # 2) Helper: get all candidate row elements
        def _get_rows():
            rows = self.driver.find_elements(
                By.CSS_SELECTOR, "div[data-testid^='ChainTableRow-']"
            )
            if not rows:
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[role='row']")
            return rows

        rows = _get_rows()
        if not rows:
            logger.error("No option rows rendered (table still loading?)")
            return None

        best_row, best_strike, best_diff = None, None, float("inf")

        # 3) Virtual tables sometimes lazy-load; scroll a bit to ensure full page
        from selenium.common.exceptions import StaleElementReferenceException

        actions = ActionChains(self.driver)
        best_xpath = None

        for _ in range(6):  # 3 down + 3 up scrolls
            # Re-query rows every pass so WebElements are always fresh
            rows = _get_rows()
            if not rows:
                break

            for row in rows:
                try:
                    strike_txt = row.find_element(
                        By.CSS_SELECTOR, "[data-testid='OptionChainStrikePriceCell'] h3"
                    ).text
                    strike_val = float(re.sub(r"[^\d.]", "", strike_txt))
                    diff = abs(strike_val - current_price)
                    if diff < best_diff:
                        best_diff = diff
                        best_strike = strike_val
                        # Build multiple stable XPATHs we can try later
                        row_testid = row.get_attribute("data-testid") or ""
                        if row_testid:
                            best_xpath = f"//div[@data-testid='{row_testid}']"
                        else:
                            # Fallback XPaths for different DOM structures
                            best_xpath = f"//h3[contains(text(), '{strike_val}')]/ancestor::div[contains(@data-testid, 'ChainTableRow')] | //h3[contains(text(), '{strike_val}')]/ancestor::tr | //*[@data-testid='OptionChainStrikePriceCell'][contains(., '{strike_val}')]/ancestor::*[1]"
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

            # Scroll down every other pass, up on the next → reaches both buffers
            scroll_dir = 1 if _ % 2 == 0 else -1
            actions.move_by_offset(0, scroll_dir * 400).perform()
            time_module.sleep(0.3)

        if not best_strike:
            logger.error("No ATM strike row found after scanning/scrolling")
            return None

        # Re-locate the row fresh so it's not stale - try multiple strategies
        best_row = None
        fallback_xpaths = [
            best_xpath,
            f"//div[@data-testid='ChainTableRow-{best_strike}']",
            f"//h3[contains(text(), '{best_strike}')]/ancestor::div[contains(@data-testid, 'ChainTableRow')]",
            f"//h3[contains(text(), '{best_strike}')]/ancestor::tr",
            f"//*[@data-testid='OptionChainStrikePriceCell'][contains(., '{best_strike}')]/ancestor::*[1]",
            f"//*[contains(text(), '{best_strike}')]/ancestor::*[contains(@data-testid, 'Row')]",
        ]

        for xpath in fallback_xpaths:
            try:
                best_row = self.driver.find_element(By.XPATH, xpath)
                logger.info(f"Successfully re-located row using XPath: {xpath[:50]}...")
                break
            except Exception as e:
                logger.debug(f"XPath failed: {xpath[:50]}... - {e}")
                continue

        if not best_row:
            logger.error(
                f"Could not re-locate ATM strike {best_strike} after scrolling"
            )
            return None

        logger.info(f"[ATM] Strike chosen: ${best_strike} (Delta={best_diff:.2f})")

        # Build a robust selector list so the buy-click flow works
        row_id = best_row.get_attribute("data-testid") or ""
        xpath_by_rowid = f"//div[@data-testid='{row_id}']" if row_id else ""
        # When the layout is a <tr>, fall back to a strike-match xpath
        strike_xpath = f"//*[contains(text(), '{best_strike}')]/ancestor::tr"

        selector_list = list(
            filter(
                None,
                [
                    xpath_by_rowid,
                    strike_xpath,
                    best_xpath,  # Include the fresh xpath we used
                ],
            )
        )

        return {
            "strike": best_strike,
            "option_type": option_type,
            "element": best_row,  # direct WebElement
            "element_selectors": selector_list,  # for click_option_and_buy
        }

    def click_option_and_buy(self, option_data: Dict, quantity: int = 1) -> bool:
        """
        Robust click option and buy flow with improved button discovery.

        Args:
            option_data: Dictionary from find_atm_option containing strike, etc.
            quantity: Number of contracts to buy

        Returns:
            True if successful (reaches Review screen)
        """
        try:
            # Extract data from option_data
            strike = option_data.get("strike")
            option_type = option_data.get("option_type")

            if not option_data.get("element") or not strike:
                logger.error("Invalid option data - missing element or strike")
                return False

            logger.info(f"Starting ROBUST order flow for {option_type} ${strike}")

            # locate the row again (non-stale) and then probe for ask/bid button
            row = option_data["element"]
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", row
            )
            time_module.sleep(0.5)

            side_key = "ask" if option_type.upper() == "CALL" else "bid"
            buttons = row.find_elements(
                By.CSS_SELECTOR, f"button[data-testid$='{side_key}']"
            )
            buttons = [b for b in buttons if b.is_displayed()]

            if not buttons:
                # fallback: first visible button with a price inside
                import re

                buttons = [
                    b
                    for b in row.find_elements(By.TAG_NAME, "button")
                    if re.search(r"\$\d+\.\d{1,2}", b.text)
                ]

            if not buttons:
                logger.error("No buy/ask button visible in ATM row")
                return False

            buy_button = buttons[0]
            logger.info(
                f"[OK] Found {side_key.upper()} button: {buy_button.text.strip()}"
            )
            self.driver.execute_script("arguments[0].click();", buy_button)
            time_module.sleep(3)

            # Step 2: Look for Continue button (simplified)
            logger.info("Looking for Continue button...")
            try:
                # Simple Continue button search
                continue_buttons = self.driver.execute_script(
                    """
                    return Array.from(document.querySelectorAll('button')).filter(
                        el => el.textContent.toLowerCase().includes('continue')
                    );
                """
                )

                if continue_buttons:
                    self.driver.execute_script(
                        "arguments[0].click();", continue_buttons[0]
                    )
                    logger.info("[OK] Clicked Continue button")
                    time_module.sleep(3)
                else:
                    logger.warning("Continue button not found, proceeding...")
            except Exception as e:
                logger.warning(f"Continue button step failed: {e}")

            # Step 3: Set quantity (simplified)
            try:
                qty_input = self.driver.find_element(
                    By.CSS_SELECTOR, "#OptionOrderForm-Quantity-FormField"
                )
                qty_input.clear()
                qty_input.send_keys(str(quantity))
                logger.info(f"[OK] Set quantity to {quantity}")
                time_module.sleep(1)
            except Exception as e:
                logger.warning(f"Could not set quantity: {e}")

            # Step 4: Look for Review Order button (simplified)
            logger.info("Looking for Review Order button...")
            try:
                review_buttons = self.driver.execute_script(
                    """
                    return Array.from(document.querySelectorAll('button')).filter(
                        el => el.textContent.toLowerCase().includes('review')
                    );
                """
                )

                if review_buttons:
                    self.driver.execute_script(
                        "arguments[0].click();", review_buttons[0]
                    )
                    logger.info("[SUCCESS] Reached Review Order screen - STOPPING HERE")
                    time_module.sleep(2)
                    return True
                else:
                    logger.warning("Review button not found")
                    return False
            except Exception as e:
                logger.error(f"Review button step failed: {e}")
                return False

        except Exception as e:
            logger.error(f"Error in robust option purchase flow: {e}")
            return False

            # Step 2: Find the buy button (green "+" button) near this strike with enhanced strategies
            buy_button = None

            # Strategy 1: Look for buy button in the same row or nearby elements
            try:
                logger.info("Strategy 1: Searching for buy button near strike element")
                parent = strike_element
                for level in range(6):  # Check up to 6 parent levels
                    try:
                        # Enhanced buy button selectors based on Robinhood structure
                        buy_button_selectors = [
                            ".//button[contains(@class, 'green')]",
                            ".//button[contains(text(), '+')]",
                            ".//button[contains(@aria-label, 'buy')]",
                            ".//button[contains(@aria-label, 'Buy')]",
                            ".//button[contains(@class, 'buy')]",
                            ".//button[contains(@class, 'ask')]",
                            ".//button[contains(@class, 'primary')]",
                            ".//button[contains(@data-testid, 'buy')]",
                            ".//button[contains(@data-testid, 'ask')]",
                        ]

                        for selector in buy_button_selectors:
                            buy_buttons = parent.find_elements(By.XPATH, selector)
                            if buy_buttons:
                                buy_button = buy_buttons[0]
                                logger.info(
                                    f"[OK] Found buy button via parent level {level}, selector: {selector}"
                                )
                                break

                        if buy_button:
                            break

                        parent = parent.find_element(By.XPATH, "..")
                    except:
                        break

            except Exception as e:
                logger.warning(f"Strategy 1 failed: {e}")

            # Strategy 2: Look for buy button in the same table row
            if not buy_button:
                try:
                    logger.info("Strategy 2: Searching for buy button in table row")
                    row_selectors = [
                        "./ancestor::tr//button",
                        "./ancestor::div[contains(@class, 'row')]//button",
                        "./ancestor::div[contains(@class, 'option')]//button",
                        "./following-sibling::*//button",
                        "./preceding-sibling::*//button",
                    ]

                    for selector in row_selectors:
                        try:
                            row_buttons = strike_element.find_elements(
                                By.XPATH, selector
                            )
                            if row_buttons:
                                # Look for buttons that might be buy buttons
                                for btn in row_buttons:
                                    btn_text = btn.text.strip().lower()
                                    btn_class = btn.get_attribute("class") or ""
                                    btn_aria = btn.get_attribute("aria-label") or ""

                                    # Check if this looks like a buy button
                                    if (
                                        "+" in btn_text
                                        or "buy" in btn_text.lower()
                                        or "green" in btn_class.lower()
                                        or "ask" in btn_class.lower()
                                        or "buy" in btn_aria.lower()
                                        or "ask" in btn_aria.lower()
                                    ):
                                        buy_button = btn
                                        logger.info(
                                            f"[OK] Found buy button via row search: {selector}"
                                        )
                                        break

                                # If no obvious buy button found, take the last button (common pattern)
                                if not buy_button and row_buttons:
                                    buy_button = row_buttons[-1]
                                    logger.info(
                                        f"[OK] Using last button in row as buy button: {selector}"
                                    )

                                if buy_button:
                                    break
                        except:
                            continue

                except Exception as e:
                    logger.warning(f"Strategy 2 failed: {e}")

            # Strategy 3: Scroll and search for buy buttons (in case they're not visible)
            if not buy_button:
                logger.info("Strategy 3: Scrolling to find buy button")
                try:
                    # Scroll the strike element into view
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        strike_element,
                    )
                    time_module.sleep(1)

                    # Try the previous strategies again after scrolling
                    parent = strike_element
                    for level in range(3):
                        try:
                            buy_buttons = parent.find_elements(By.XPATH, ".//button")
                            for btn in buy_buttons:
                                if btn.is_displayed() and btn.is_enabled():
                                    btn_text = btn.text.strip()
                                    btn_class = btn.get_attribute("class") or ""

                                    if (
                                        "+" in btn_text
                                        or "green" in btn_class.lower()
                                        or "ask" in btn_class.lower()
                                        or "buy" in btn_class.lower()
                                    ):
                                        buy_button = btn
                                        logger.info(
                                            f"[OK] Found buy button after scrolling at level {level}"
                                        )
                                        break

                            if buy_button:
                                break

                            parent = parent.find_element(By.XPATH, "..")
                        except:
                            break

                except Exception as e:
                    logger.warning(f"Strategy 3 failed: {e}")

            # Strategy 4: Look for any clickable button near the strike (last resort)
            if not buy_button:
                logger.info(
                    "Strategy 4: Looking for any clickable button near strike (last resort)"
                )
                try:
                    # Find all buttons near the strike element
                    nearby_buttons = strike_element.find_elements(
                        By.XPATH,
                        "./ancestor::*[position()<=3]//button | ./following::button[position()<=5] | ./preceding::button[position()<=5]",
                    )

                    for btn in nearby_buttons:
                        try:
                            if btn.is_displayed() and btn.is_enabled():
                                buy_button = btn
                                logger.info(
                                    "[OK] Using nearby clickable button as buy button (last resort)"
                                )
                                break
                        except:
                            continue

                except Exception as e:
                    logger.warning(f"Strategy 4 failed: {e}")

            if not buy_button:
                logger.error(
                    "Could not find buy button for this option using any strategy"
                )
                # Debug: Show what buttons are available
                try:
                    all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    visible_buttons = [btn for btn in all_buttons if btn.is_displayed()]
                    logger.info(
                        f"Found {len(visible_buttons)} visible buttons on page for debugging"
                    )
                    for i, btn in enumerate(visible_buttons[:10]):  # Show first 10
                        try:
                            btn_text = btn.text.strip()[:50]  # Limit text length
                            btn_class = (btn.get_attribute("class") or "")[:50]
                            logger.info(
                                f"  Button {i+1}: text='{btn_text}', class='{btn_class}'"
                            )
                        except:
                            pass
                except:
                    logger.warning("Could not retrieve debug button information")
                return False

            logger.info(
                f"Step 1: Clicking Ask Price button for {option_type} ${strike} option"
            )

            # Step 1: Click the Ask Price button (green button with price)
            self.driver.execute_script("arguments[0].click();", buy_button)
            time_module.sleep(2)

            # Step 2: Wait for OptionChainOrderFormHeader to appear
            logger.info("Step 2: Waiting for OptionChainOrderFormHeader to load")
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "[data-testid='OptionChainOrderFormHeader']")
                    )
                )
                logger.info("[OK] OptionChainOrderFormHeader loaded")
            except TimeoutException:
                logger.warning(
                    "OptionChainOrderFormHeader not found, proceeding anyway"
                )

            # Step 3: Look for and click the Continue button
            logger.info("Step 3: Looking for Continue button")
            continue_button = None

            # Look for Continue button with various strategies
            continue_selectors = [
                "button:contains('Continue')",
                "[data-testid*='continue']",
                "button[type='submit']",
                "button.primary",
                "button[class*='primary']",
            ]

            for selector in continue_selectors:
                try:
                    if ":contains" in selector:
                        # Use JavaScript to find Continue button
                        buttons = self.driver.execute_script(
                            """
                            return Array.from(document.querySelectorAll('button')).filter(
                                el => el.textContent.toLowerCase().includes('continue')
                            );
                            """
                        )
                        if buttons:
                            continue_button = buttons[0]
                            break
                    else:
                        continue_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        break
                except:
                    continue

            if continue_button:
                logger.info("[OK] Found Continue button, clicking")
                self.driver.execute_script("arguments[0].click();", continue_button)
                time_module.sleep(3)
            else:
                logger.warning(
                    "Continue button not found, proceeding to quantity setting"
                )

            # Step 4: Set quantity if different from 1 (on the contract selection screen)
            if quantity != 1:
                logger.info(f"Step 4: Setting quantity to {quantity}")

                # Look for quantity input field on the contract selection screen
                quantity_selectors = [
                    "#OptionOrderForm-Quantity-FormField",
                    "input[name*='quantity']",
                    "input[name*='contracts']",
                    "input[placeholder*='quantity']",
                    "input[placeholder*='Quantity']",
                    "input[placeholder*='Contracts']",
                    "[data-testid*='quantity'] input",
                    "[data-testid*='contracts'] input",
                    "input[value='1']",
                ]

                quantity_set = False
                for selector in quantity_selectors:
                    try:
                        qty_input = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        qty_input.clear()
                        qty_input.send_keys(str(quantity))
                        time_module.sleep(1)
                        quantity_set = True
                        logger.info(f"[OK] Successfully set quantity to {quantity}")
                        break
                    except:
                        continue

                if not quantity_set:
                    logger.warning(
                        f"Could not set quantity to {quantity}, proceeding with default"
                    )

            # Step 5: Look for Review Order button (final step)
            logger.info("Step 5: Looking for Review Order button")

            # Wait a moment for the page to update after quantity change
            time_module.sleep(2)

            review_selectors = [
                "button:contains('Review Order')",
                "button:contains('Review')",
                "[data-testid*='review']",
                "button[type='submit']",
                "button.primary",
                "button[class*='primary']",
                "button:contains('Continue')",
                "button:contains('Next')",
            ]

            review_button = None
            for selector in review_selectors:
                try:
                    if ":contains" in selector:
                        # Use JavaScript to find Review Order button
                        text_to_find = selector.split("')")[0].split("'")
                        if len(text_to_find) > 1:
                            text = text_to_find[1]
                            buttons = self.driver.execute_script(
                                """
                                return Array.from(document.querySelectorAll('button')).filter(
                                    el => el.textContent.toLowerCase().includes(arguments[0].toLowerCase())
                                );
                                """,
                                text,
                            )
                            if buttons:
                                review_button = buttons[0]
                                logger.info(
                                    f"[OK] Found '{text}' button via JavaScript"
                                )
                                break
                    else:
                        review_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        logger.info(
                            f"[OK] Found review button via selector: {selector}"
                        )
                        break
                except:
                    continue

            if review_button:
                logger.info(
                    "Step 6: Clicking Review Order button to reach final review screen"
                )
                self.driver.execute_script("arguments[0].click();", review_button)
                time_module.sleep(3)

                # Wait for final review screen to load
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda driver: "review" in driver.current_url.lower()
                        or len(
                            driver.find_elements(
                                By.XPATH,
                                "//*[contains(text(), 'Review') or contains(text(), 'Submit') or contains(text(), 'Place Order')]",
                            )
                        )
                        > 0
                    )
                    logger.info(
                        "[SUCCESS] Reached final Review Order screen"
                    )
                    
                    # Check if unattended mode with entry approval is enabled
                    if self._should_auto_approve_entry():
                        return self._handle_llm_entry_approval()
                    else:
                        logger.info("[MANUAL ACTION REQUIRED] Please review the order details and submit manually if approved")
                        return True
                except:
                    logger.info(
                        "[SUCCESS] Order flow completed - STOPPING HERE for manual review"
                    )
                    logger.info(
                        "[MANUAL ACTION REQUIRED] Please review the order details and submit manually if approved"
                    )
                    return True
            else:
                logger.warning(
                    "Could not find Review Order button, but order flow may be complete"
                )
                logger.info("[SUCCESS] STOPPING HERE for manual review")
                logger.info(
                    "[MANUAL ACTION REQUIRED] Please review the order details and submit manually if approved"
                )
                return True

        except Exception as e:
            logger.error(f"Error in option purchase flow: {e}")
            return False

    def get_option_premium(self) -> Optional[float]:
        """
        Extract option premium from the current page - FAST VERSION.
        Optimized for speed and accuracy in live trading.

        Returns:
            Option premium as float or None
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # Fast Strategy 1: Look for "Ask $X.XX" pattern (most common)
            try:
                # Use JavaScript for fastest extraction
                premium = self.driver.execute_script(
                    """
                    // Look for Ask price pattern
                    const askElements = Array.from(document.querySelectorAll('*')).filter(
                        el => el.textContent && el.textContent.match(/Ask\s*\$\d+\.\d{2}/i)
                    );
                    
                    for (let el of askElements) {
                        const match = el.textContent.match(/Ask\s*\$([\d.]+)/i);
                        if (match) {
                            const price = parseFloat(match[1]);
                            if (price >= 0.01 && price <= 100) {
                                return price;
                            }
                        }
                    }
                    
                    // Look for Bid/Ask format
                    const bidAskElements = Array.from(document.querySelectorAll('*')).filter(
                        el => el.textContent && el.textContent.match(/Bid\s*\$[\d.]+\s*•\s*Ask\s*\$[\d.]+/i)
                    );
                    
                    for (let el of bidAskElements) {
                        const match = el.textContent.match(/Ask\s*\$([\d.]+)/i);
                        if (match) {
                            const price = parseFloat(match[1]);
                            if (price >= 0.01 && price <= 100) {
                                return price;
                            }
                        }
                    }
                    
                    return null;
                    """
                )

                if premium:
                    logger.info(f"[FAST] Found option premium: ${premium:.2f}")
                    return premium
            except Exception as e:
                logger.debug(f"Fast strategy 1 failed: {e}")

            # Fast Strategy 2: Look in order form area
            try:
                # Wait briefly for order form to load
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "[class*='order'], [class*='Order'], [data-testid*='order']",
                        )
                    )
                )

                premium = self.driver.execute_script(
                    """
                    // Look in order form area
                    const orderForms = document.querySelectorAll('[class*="order"], [class*="Order"], [data-testid*="order"]');
                    
                    for (let form of orderForms) {
                        const text = form.textContent || '';
                        const matches = text.match(/\$([\d.]+)/g);
                        
                        if (matches) {
                            for (let match of matches) {
                                const price = parseFloat(match.replace('$', ''));
                                if (price >= 0.01 && price <= 100) {
                                    return price;
                                }
                            }
                        }
                    }
                    
                    return null;
                    """
                )

                if premium:
                    logger.info(
                        f"[FAST] Found option premium in order form: ${premium:.2f}"
                    )
                    return premium
            except Exception as e:
                logger.debug(f"Fast strategy 2 failed: {e}")

            # Fast Strategy 3: Quick DOM scan for price patterns
            try:
                premium = self.driver.execute_script(
                    """
                    // Quick scan for any reasonable price
                    const allText = document.body.textContent || '';
                    const priceMatches = allText.match(/\$([0-9]+\.[0-9]{2})/g);
                    
                    if (priceMatches) {
                        for (let match of priceMatches) {
                            const price = parseFloat(match.replace('$', ''));
                            if (price >= 0.01 && price <= 100) {
                                return price;
                            }
                        }
                    }
                    
                    return null;
                    """
                )

                if premium:
                    logger.info(
                        f"[FAST] Found option premium (DOM scan): ${premium:.2f}"
                    )
                    return premium
            except Exception as e:
                logger.debug(f"Fast strategy 3 failed: {e}")

            logger.warning("[FAST] Could not extract option premium quickly")
            return None

        except Exception as e:
            logger.error(f"Error getting option premium: {e}")
            return None

    def take_screenshot(self, filename: str = None) -> str:
        """
        Take a screenshot of the current page.

        Args:
            filename: Optional filename for screenshot

        Returns:
            Path to saved screenshot
        """
        try:
            if not filename:
                timestamp = int(time_module.time())
                filename = f"screenshot_{timestamp}.png"

            screenshot_path = Path("logs") / filename
            screenshot_path.parent.mkdir(exist_ok=True)

            self.driver.save_screenshot(str(screenshot_path))
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)

        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""

    def wait_for_manual_action(self, message: str = "Press Enter to continue..."):
        """Wait for manual user input before continuing."""
        print(f"\n🚨 {message}")
        input("✅ Press Enter when ready to continue...")

    def navigate_to_positions(self) -> bool:
        """
        Navigate to the Robinhood positions page.

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info("[POSITIONS] Navigating to positions page...")

            # Try different URLs and navigation methods for positions
            positions_urls = [
                "https://robinhood.com/positions",
                "https://robinhood.com/account/positions",
                "https://robinhood.com/portfolio",
            ]

            for url in positions_urls:
                try:
                    self.driver.get(url)
                    time_module.sleep(3)

                    # Check if we're on a positions-related page
                    if any(
                        keyword in self.driver.current_url.lower()
                        for keyword in ["position", "portfolio", "account"]
                    ):
                        logger.info(
                            f"Successfully navigated to positions page: {self.driver.current_url}"
                        )
                        return True

                except Exception as e:
                    logger.warning(f"Failed to navigate to {url}: {e}")
                    continue

            # Try clicking on navigation menu items
            nav_selectors = [
                "a[href*='position']",
                "a[href*='portfolio']",
                "button:contains('Positions')",
                "[data-testid*='position']",
                "[data-testid*='portfolio']",
            ]

            for selector in nav_selectors:
                try:
                    if ":contains" in selector:
                        elements = self.driver.execute_script(
                            """
                            return Array.from(document.querySelectorAll('button, a')).filter(
                                el => el.textContent.toLowerCase().includes('position') ||
                                      el.textContent.toLowerCase().includes('portfolio')
                            );
                        """
                        )
                        if elements:
                            self.driver.execute_script(
                                "arguments[0].click();", elements[0]
                            )
                            time_module.sleep(3)
                            break
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        self.driver.execute_script("arguments[0].click();", element)
                        time_module.sleep(3)
                        break
                except:
                    continue

            # Final check if we're on positions page
            current_url = self.driver.current_url.lower()
            if any(
                keyword in current_url
                for keyword in ["position", "portfolio", "account"]
            ):
                logger.info("Successfully navigated to positions page")
                return True

            logger.error("Could not navigate to positions page")
            return False

        except Exception as e:
            logger.error(f"Error navigating to positions: {e}")
            return False

    def find_position_to_close(self, symbol: str, side: str, strike: float) -> bool:
        """
        Find and select a specific position to close.

        Args:
            symbol: Stock symbol (e.g., 'SPY')
            side: Option side ('CALL' or 'PUT')
            strike: Strike price

        Returns:
            True if position found and selected, False otherwise
        """
        try:
            logger.info(f"[CLOSE] Looking for {symbol} {side} ${strike} position...")

            # Wait for positions to load
            time_module.sleep(3)

            # Look for position rows/cards containing our criteria
            position_selectors = [
                "[data-testid*='position']",
                ".position-row",
                ".position-card",
                "[class*='position']",
                "tr",
                "div[class*='row']",
            ]

            position_elements = []
            for selector in position_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        position_elements.extend(elements)
                except:
                    continue

            if not position_elements:
                logger.error("No position elements found on page")
                return False

            # Search through position elements for matching criteria
            for element in position_elements:
                try:
                    element_text = element.text.lower()

                    # Check if this element contains our position criteria
                    if (
                        symbol.lower() in element_text
                        and side.lower() in element_text
                        and str(strike) in element_text
                    ):

                        logger.info(f"Found matching position: {element_text[:100]}...")

                        # Try to click on the position or find a close/sell button
                        close_selectors = [
                            "button:contains('Sell')",
                            "button:contains('Close')",
                            "[data-testid*='sell']",
                            "[data-testid*='close']",
                        ]

                        # First try to find close/sell button within this position element
                        for close_selector in close_selectors:
                            try:
                                if ":contains" in close_selector:
                                    buttons = element.find_elements(
                                        By.XPATH,
                                        ".//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sell') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
                                    )
                                    if buttons:
                                        self.driver.execute_script(
                                            "arguments[0].click();", buttons[0]
                                        )
                                        time_module.sleep(2)
                                        logger.info("Clicked close/sell button")
                                        return True
                                else:
                                    close_button = element.find_element(
                                        By.CSS_SELECTOR, close_selector
                                    )
                                    self.driver.execute_script(
                                        "arguments[0].click();", close_button
                                    )
                                    time_module.sleep(2)
                                    logger.info("Clicked close/sell button")
                                    return True
                            except:
                                continue

                        # If no close button found, try clicking the position itself
                        try:
                            self.driver.execute_script("arguments[0].click();", element)
                            time_module.sleep(2)
                            logger.info("Clicked on position element")
                            return True
                        except:
                            continue

                except Exception:
                    continue

            logger.error(f"Could not find position: {symbol} {side} ${strike}")
            return False

        except Exception as e:
            logger.error(f"Error finding position to close: {e}")
            return False

    def execute_close_order(self, contracts: int) -> bool:
        """
        Execute the close order flow (Sell to Close).

        Args:
            contracts: Number of contracts to close

        Returns:
            True if order setup successful and halted at Review, False otherwise
        """
        try:
            logger.info(
                f"[CLOSE] Setting up sell to close order for {contracts} contracts..."
            )

            # Wait for close order page to load
            time_module.sleep(3)

            # Look for "Sell to Close" or similar options
            sell_to_close_selectors = [
                "button:contains('Sell to Close')",
                "button:contains('Sell')",
                "[data-testid*='sell-to-close']",
                "[data-testid*='sell']",
            ]

            for selector in sell_to_close_selectors:
                try:
                    if ":contains" in selector:
                        buttons = self.driver.execute_script(
                            """
                            return Array.from(document.querySelectorAll('button')).filter(
                                el => el.textContent.toLowerCase().includes('sell')
                            );
                        """
                        )
                        if buttons:
                            self.driver.execute_script(
                                "arguments[0].click();", buttons[0]
                            )
                            time_module.sleep(2)
                            break
                    else:
                        button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        self.driver.execute_script("arguments[0].click();", button)
                        time_module.sleep(2)
                        break
                except:
                    continue

            # Set quantity if needed
            quantity_selectors = [
                "#OptionOrderForm-Quantity-FormField",
                "input[placeholder*='quantity']",
                "input[placeholder*='contracts']",
                "[data-testid*='quantity'] input",
            ]

            for selector in quantity_selectors:
                try:
                    qty_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    qty_input.clear()
                    qty_input.send_keys(str(contracts))
                    time_module.sleep(1)
                    break
                except:
                    continue

            # Look for Review Order button
            review_selectors = [
                "button:contains('Review')",
                "button:contains('Review Order')",
                "[data-testid*='review']",
                "button.primary:contains('Review')",
            ]

            review_button = None
            for selector in review_selectors:
                try:
                    if ":contains" in selector:
                        buttons = self.driver.execute_script(
                            """
                            return Array.from(document.querySelectorAll('button')).filter(
                                el => el.textContent.toLowerCase().includes('review')
                            );
                        """
                        )
                        if buttons:
                            review_button = buttons[0]
                            break
                    else:
                        review_button = self.driver.find_element(
                            By.CSS_SELECTOR, selector
                        )
                        break
                except:
                    continue

            if review_button:
                self.driver.execute_script("arguments[0].click();", review_button)
                logger.info(
                    "[CLOSE] Reached Review Order screen for CLOSE - STOPPING HERE"
                )
                return True
            else:
                logger.warning("Could not find Review Order button for close")
                return False

        except Exception as e:
            logger.error(f"Error in close order flow: {e}")
            return False

    def quit(self):
        """Close the browser and cleanup resources."""
        if self.driver:
            try:
                # Close all windows first
                for handle in self.driver.window_handles:
                    try:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    except:
                        pass

                # Quit the driver
                self.driver.quit()
                logger.info("Browser closed successfully")

            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.driver = None

                # Cleanup temp profile directory (C-3)
                if self._temp_profile_dir and Path(self._temp_profile_dir).exists():
                    try:
                        shutil.rmtree(self._temp_profile_dir)
                        logger.info(f"Cleaned up temp profile: {self._temp_profile_dir}")
                        self._temp_profile_dir = None
                    except Exception as cleanup_error:
                        logger.warning(f"Could not cleanup temp profile: {cleanup_error}")

                # Force cleanup any remaining Chrome processes
                try:
                    import psutil

                    time_module.sleep(1)  # Give processes time to close naturally

                    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                        try:
                            if "chrome" in proc.info["name"].lower() and any(
                                "--remote-debugging-port" in arg
                                for arg in proc.info.get("cmdline", [])
                            ):
                                proc.terminate()
                                logger.info(
                                    f"Terminated hanging Chrome process {proc.info['pid']}"
                                )
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception as cleanup_error:
                    logger.warning(f"Chrome cleanup failed: {cleanup_error}")
