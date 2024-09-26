import asyncio
from pyppeteer import launch

async def capture_screenshot(url, output_file):
    try:
        browser = await launch(headless=True, args=['--no-sandbox'])
        page = await browser.newPage()
        await page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 60000})
        await page.screenshot({'path': output_file, 'fullPage': True})
        print(f"Screenshot saved to {output_file}")
        await browser.close()
    except Exception as e:
        print(f"Error capturing screenshot: {e}")

if __name__ == '__main__':
    url = 'https://www.example.com'  # Replace with your target URL
    output_file = 'screenshot.png'    # Replace with your desired output file name
    asyncio.get_event_loop().run_until_complete(capture_screenshot(url, output_file))
