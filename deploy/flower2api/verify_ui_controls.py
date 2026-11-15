"""验证开发预览页实际使用的 Vue 通用控件，全部使用本地示例。"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def verify(url: str, output: Path) -> None:
    """运行控件契约及弹窗、触屏验证。@param url 组件预览地址。@param output 证据目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    business_requests = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: business_requests.append(request.url) if any(path in request.url for path in ("/admin/", "/api/", "/v1/")) else None)
        await page.goto(url)
        number = page.get_by_role("spinbutton", name="并发上限", exact=True)
        await number.fill("1")
        await expect(page.get_by_role("button", name="减少并发上限", exact=True)).to_be_disabled()
        await page.get_by_role("button", name="增加并发上限", exact=True).click()
        await expect(number).to_have_value("2")
        await number.fill("")
        await page.get_by_role("button", name="保存示例").click()
        await expect(page.get_by_test_id("form-result")).to_have_text("尚未保存")
        await number.fill("3")
        await page.get_by_role("spinbutton", name="小数步长示例").fill("0.5")
        await page.get_by_role("button", name="增加小数步长示例").click()
        await expect(page.get_by_role("spinbutton", name="小数步长示例")).to_have_value("0.6")
        await expect(page.get_by_role("spinbutton", name="禁用数字输入")).to_be_disabled()
        await expect(page.get_by_role("combobox", name="禁用选择")).to_be_disabled()
        choice = page.get_by_role("combobox", name="订阅类型", exact=True)
        await choice.click()
        await expect(page.get_by_role("option", name="Enterprise（暂不可用）", exact=True)).to_be_disabled()
        await page.get_by_role("option", name="未设置", exact=True).click()
        await expect(choice).to_contain_text("未设置")
        await page.get_by_role("button", name="保存示例").click()
        result = json.loads(await page.get_by_test_id("form-result").inner_text())
        assert result["subscription"] == "", result
        assert result["concurrency"] == "3", result
        await choice.focus()
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("p")
        await page.keyboard.press("Enter")
        await expect(choice).to_contain_text("Pro")
        await choice.click()
        await page.keyboard.press("Escape")
        await expect(choice).to_be_focused()
        search = page.get_by_role("searchbox", name="会话搜索")
        await search.fill("abcd")
        await search.dispatch_event("keydown", {"key": "Enter", "isComposing": True})
        await expect(page.get_by_test_id("search-result")).to_contain_text("—")
        await search.press("Enter")
        await expect(page.get_by_test_id("search-result")).to_contain_text("abcd")
        assert await search.evaluate("el => getComputedStyle(el).outlineStyle") == "none"
        await page.get_by_role("button", name="清空会话搜索").click()
        await expect(search).to_have_value("")
        await expect(search).to_be_focused()
        trigger = page.get_by_role("button", name="查看用量统计", exact=True)
        await trigger.hover()
        await expect(page.locator(".fui-info-content")).to_be_visible()
        await expect(page.locator(".fui-info-content")).to_contain_text("$15.16")
        await page.screenshot(path=str(output / "vue-controls.png"), full_page=True)
        await page.keyboard.press("Escape")
        await expect(page.locator(".fui-info-content")).to_have_count(0)
        await page.get_by_role("button", name="打开窗口示例").click()
        dialog = page.get_by_role("dialog")
        modal_choice = page.get_by_role("combobox", name="窗口内授权方式")
        await modal_choice.click()
        await page.get_by_role("option", name="Setup Token", exact=True).click()
        await expect(modal_choice).to_contain_text("Setup Token")
        await modal_choice.click()
        await page.keyboard.press("Escape")
        await expect(dialog).to_be_visible()
        modal_tooltip = page.get_by_role("button", name="查看授权说明", exact=True)
        await modal_tooltip.click()
        await expect(page.locator(".fui-info-content")).to_be_visible()
        await page.keyboard.press("Escape")
        await expect(page.locator(".fui-info-content")).to_have_count(0)
        await expect(dialog).to_be_visible()
        await page.get_by_role("button", name="关闭窗口", exact=True).click()
        for width in (720, 390):
            await page.set_viewport_size({"width": width, "height": 900})
            await choice.click()
            menu = page.locator(".fui-choice-menu")
            await expect(menu).to_be_visible()
            box = await menu.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width, box
            await page.screenshot(path=str(output / f"vue-controls-{width}.png"), full_page=True)
            await page.keyboard.press("Escape")
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        touch = await browser.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True)
        touch_page = await touch.new_page()
        await touch_page.goto(url)
        touch_choice = touch_page.get_by_role("combobox", name="订阅类型", exact=True)
        await touch_choice.tap()
        await touch_page.get_by_role("option", name="Ultra", exact=True).tap()
        await expect(touch_choice).to_contain_text("Ultra")
        await touch_page.get_by_role("button", name="查看用量统计", exact=True).tap()
        await expect(touch_page.locator(".fui-info-content")).to_be_visible()
        await browser.close()
    assert not errors, errors
    assert not business_requests, business_requests
    (output / "verification.json").write_text(json.dumps({"passed": True, "errors": errors, "business_requests": business_requests, "scenes": ["数字边界、空值、步长、禁用", "空选项表单原值、键盘与禁用选项", "搜索整体焦点及提交清空", "气泡完整数据和触屏", "原生dialog内菜单气泡及Esc层级", "720/390px视口布局"]}, ensure_ascii=False, indent=2))
    print("Vue 复用控件验证通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="验证本地 Vue 控件预览")
    parser.add_argument("--url", default="http://127.0.0.1:4187/ui-preview.html")
    parser.add_argument("--output", type=Path, default=Path(".deploy/frontend-sidebar-refresh/ui-controls"))
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.output))
