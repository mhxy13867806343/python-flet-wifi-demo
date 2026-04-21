import flet as ft
from wifi_scanner import scan_wifi_list, get_known_wifi_ssids, get_wifi_password, connect_wifi
from db import init_db, get_all_passwords, save_password

def main(page: ft.Page):
    # 使用 AppBar 替代窗口的 Title
    page.title = "跨平台 Wi-Fi 管理器"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.window_width = 800
    page.window_height = 600

    error_bar = ft.Container(
        content=ft.Text("", color=ft.Colors.ON_ERROR_CONTAINER),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        padding=10,
        border_radius=8,
        visible=False,
    )

    # 初始化数据库
    init_db()
    
    password_cache = get_all_passwords()
    selected_wifi = {"ssid": "", "bssid": "", "signal": None, "security": ""}

    toast_text = ft.Text("", color=ft.Colors.WHITE, size=13)
    toast_container = ft.Container(
        content=toast_text,
        bgcolor=ft.Colors.BLACK,
        padding=12,
        border_radius=10,
        opacity=0.9,
        visible=False,
        right=20,
        bottom=56,
    )
    page.overlay.append(toast_container)
    toast_timer = {"t": None}

    def show_message(message: str):
        toast_text.value = message
        toast_container.visible = True
        page.update()
        t = toast_timer.get("t")
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        import threading
        def _hide():
            toast_container.visible = False
            page.update()
        toast_timer["t"] = threading.Timer(2.5, _hide)
        toast_timer["t"].daemon = True
        toast_timer["t"].start()

    # 右侧详情面板的内容
    detail_title = ft.Text("请选择一个 Wi-Fi", size=24, weight=ft.FontWeight.BOLD)
    detail_ssid = ft.Text("SSID: -", size=16)
    detail_bssid = ft.Text("BSSID: -", size=16)
    detail_signal = ft.Text("信号强度: -", size=16)
    detail_security = ft.Text("安全性: -", size=16)
    
    # 密码输入框和连接按钮（暂未实现功能）
    password_input = ft.TextField(
        label="输入密码 (连接时需要)",
        password=True,
        can_reveal_password=True,
        visible=False,
        width=300
    )
    def on_connect_click(e):
        ssid = (selected_wifi.get("ssid") or "").strip()
        pwd = (password_input.value or "").strip()
        ok, err = connect_wifi(ssid, pwd)
        if ok:
            show_message("已发起连接")
        else:
            show_message(err or "连接失败")
        
    connect_btn = ft.ElevatedButton("连接", visible=False, on_click=on_connect_click)

    def on_get_password(_):
        ssid = (selected_wifi.get("ssid") or "").strip()
        if not ssid or ssid in ("<隐藏网络>",):
            show_message("该网络无法直接读取密码")
            return
        if selected_wifi.get("security") in ("Open", "Unknown"):
            show_message("该网络不需要密码")
            return
            
        pwd = get_wifi_password(ssid)
        if not pwd:
            show_message("未读取到已保存的密码（可能未保存，或在系统钥匙串里需要重复授权）")
            return
            
        # 存入缓存并持久化到 SQLite 数据库
        password_cache[ssid] = pwd
        save_password(ssid, pwd)
        
        password_input.value = pwd
        password_input.visible = True
        get_password_btn.visible = False
        page.update()
        update_cached_list()
        
    get_password_btn = ft.ElevatedButton("查看已保存密码", visible=False, on_click=on_get_password)

    details_column = ft.Column(
        controls=[
            detail_title,
            ft.Divider(),
            detail_ssid,
            detail_bssid,
            detail_signal,
            detail_security,
            ft.Container(height=20),
            get_password_btn,
            password_input,
            connect_btn
        ],
        spacing=10,
    )

    details_container = ft.Container(
        content=details_column,
        padding=20,
        bgcolor=ft.Colors.SURFACE,
        border_radius=10,
        expand=True,
    )

    # 点击 Wi-Fi 列表项的处理函数
    def on_wifi_select(e, wifi_info):
        selected_wifi.update(wifi_info)
        ssid = wifi_info["ssid"]
        detail_title.value = ssid
        detail_ssid.value = f"SSID: {ssid}"
        detail_bssid.value = f"BSSID: {wifi_info['bssid']}"
        if wifi_info.get("signal") is None:
            detail_signal.value = "信号强度: -"
        else:
            detail_signal.value = f"信号强度: {wifi_info['signal']} dBm"
        detail_security.value = f"安全性: {wifi_info['security']}"

        # 核心逻辑：从缓存中读取密码，如果有则直接展示
        if ssid in password_cache:
            password_input.value = password_cache[ssid]
            password_input.visible = True
            get_password_btn.visible = False
        else:
            password_input.value = ""
            # 如果是已知网络或者加密网络，允许获取密码和输入密码
            if wifi_info["security"] not in ["Open", "Unknown"]:
                password_input.visible = True
                get_password_btn.visible = True
            else:
                password_input.visible = False
                get_password_btn.visible = False
                
        connect_btn.visible = True
        page.update()
        update_cached_list()

    wifi_list_view = ft.ListView(expand=True, spacing=10)
    cached_list_view = ft.ListView(expand=True, spacing=10)
    last_scanned_all = []
    
    content_area = ft.Container(content=wifi_list_view, expand=True)
    
    def set_tab(idx):
        if idx == 0:
            btn_all.style = ft.ButtonStyle(color=ft.Colors.BLUE)
            btn_cached.style = ft.ButtonStyle(color=ft.Colors.GREY)
            content_area.content = wifi_list_view
        else:
            btn_all.style = ft.ButtonStyle(color=ft.Colors.GREY)
            btn_cached.style = ft.ButtonStyle(color=ft.Colors.BLUE)
            content_area.content = cached_list_view
            update_cached_list()
        page.update()

    btn_all = ft.TextButton("所有网络", on_click=lambda e: set_tab(0))
    btn_cached = ft.TextButton("已查密码", on_click=lambda e: set_tab(1))
    tabs_row = ft.Row([btn_all, btn_cached], alignment=ft.MainAxisAlignment.START)
    set_tab(0)

    def update_cached_list():
        cached_list_view.controls.clear()
        
        has_cached = False
        for ssid, pwd in password_cache.items():
            has_cached = True
            
            # 从所有扫描到的网络里找对应信息
            target_w = {"ssid": ssid, "bssid": "-", "signal": None, "security": "Known"}
            
            # 找到最近一次的信息来更新显示
            for w in last_scanned_all:
                if w["ssid"] == ssid:
                    target_w = w
                    break
                    
            def create_click_handler(w):
                return lambda e: on_wifi_select(e, w)

            signal = target_w.get("signal")
            if signal is None:
                icon_color = ft.Colors.GREY
                subtitle = ft.Text(f"信号: - | {target_w['security']}")
            else:
                icon_color = ft.Colors.GREEN if signal > -60 else ft.Colors.ORANGE
                subtitle = ft.Text(f"信号: {signal} dBm | {target_w['security']}")

            cached_list_view.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.WIFI, color=icon_color),
                    title=ft.Text(ssid, weight=ft.FontWeight.BOLD),
                    subtitle=subtitle,
                    on_click=create_click_handler(target_w),
                )
            )
            
        if not has_cached:
            cached_list_view.controls.append(
                ft.Container(
                    height=180,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        [
                            ft.Text("暂无已查看过密码的网络", size=14, color=ft.Colors.GREY),
                            ft.Text("提示：先选择 Wi‑Fi → 点击“查看已保存密码”", size=12, color=ft.Colors.GREY),
                        ],
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
            
        page.update()
    known_header = ft.Text("已知网络", size=14, weight=ft.FontWeight.BOLD)
    other_header = ft.Text("其他网络", size=14, weight=ft.FontWeight.BOLD)

    def _add_tile(wifi, search_text=""):
        def create_click_handler(w):
            return lambda e: on_wifi_select(e, w)

        signal = wifi.get("signal")
        if signal is None:
            icon_color = ft.Colors.GREY
            subtitle = ft.Text(f"信号: - | {wifi['security']}")
        else:
            icon_color = ft.Colors.GREEN if signal > -60 else ft.Colors.ORANGE
            subtitle = ft.Text(f"信号: {signal} dBm | {wifi['security']}")

        # 搜索高亮逻辑
        ssid_str = wifi["ssid"]
        if search_text and search_text.lower() in ssid_str.lower():
            # 找到匹配的位置进行高亮
            start_idx = ssid_str.lower().find(search_text.lower())
            end_idx = start_idx + len(search_text)
            
            title_spans = [
                ft.TextSpan(ssid_str[:start_idx]),
                ft.TextSpan(ssid_str[start_idx:end_idx], style=ft.TextStyle(color=ft.Colors.BLUE, weight=ft.FontWeight.BOLD)),
                ft.TextSpan(ssid_str[end_idx:]),
            ]
            title_ctrl = ft.Text(spans=title_spans, weight=ft.FontWeight.BOLD)
        else:
            title_ctrl = ft.Text(ssid_str, weight=ft.FontWeight.BOLD)

        wifi_list_view.controls.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.WIFI, color=icon_color),
                title=title_ctrl,
                subtitle=subtitle,
                on_click=create_click_handler(wifi),
            )
        )

    def refresh_wifi(_=None, search_text=""):
        wifi_list_view.controls.clear()

        # 如果没有缓存过所有扫描数据，或者是点击刷新按钮强制刷新
        nonlocal last_scanned_all
        if not last_scanned_all or getattr(_, "control", None) and isinstance(_.control, ft.IconButton):
            scanned, err = scan_wifi_list()
            last_scanned_all = scanned
            
        scanned = last_scanned_all
        known = set(get_known_wifi_ssids())

        if err:
            error_bar.content.value = err
            error_bar.visible = True
        else:
            error_bar.visible = False

        scanned_by_ssid = {w["ssid"]: w for w in scanned}
        known_in_range = []
        known_not_in_range = []
        other_in_range = []

        for ssid in sorted(known):
            if ssid in scanned_by_ssid:
                known_in_range.append(scanned_by_ssid[ssid])
            else:
                known_not_in_range.append(
                    {"ssid": ssid, "bssid": "-", "signal": None, "security": "Known"}
                )

        for w in scanned:
            if w["ssid"] not in known:
                other_in_range.append(w)

        if known_in_range or known_not_in_range:
            filtered_known = []
            for w in known_in_range + known_not_in_range:
                if not search_text or search_text.lower() in w["ssid"].lower():
                    filtered_known.append(w)
                    
            if filtered_known:
                wifi_list_view.controls.append(known_header)
                for w in filtered_known:
                    _add_tile(w, search_text)

        if other_in_range:
            filtered_other = []
            for w in other_in_range:
                if not search_text or search_text.lower() in w["ssid"].lower():
                    filtered_other.append(w)
                    
            if filtered_other:
                wifi_list_view.controls.append(other_header)
                for w in filtered_other:
                    _add_tile(w, search_text)

        if not wifi_list_view.controls:
            if search_text:
                wifi_list_view.controls.append(
                    ft.Container(
                        content=ft.Text(f"未找到包含 '{search_text}' 的网络", color=ft.Colors.GREY),
                        padding=20
                    )
                )
            else:
                wifi_list_view.controls.append(
                    ft.Container(
                        content=ft.Text("未扫描到 Wi-Fi", color=ft.Colors.GREY),
                        padding=20
                    )
                )

        page.update()
        update_cached_list()

    def on_search_change(e):
        search_text = e.control.value
        refresh_wifi(search_text=search_text)

    search_box = ft.TextField(
        hint_text="搜索 Wi-Fi...",
        prefix_icon=ft.Icons.SEARCH,
        on_change=on_search_change,
        height=40,
        content_padding=0,
        border_radius=20,
    )

    list_container = ft.Container(
        content=ft.Column([
            ft.Row(
                [
                    ft.Text("Wi‑Fi", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(icon=ft.Icons.REFRESH, on_click=lambda e: refresh_wifi()),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            search_box,
            ft.Divider(),
            error_bar,
            tabs_row,
            content_area
        ]),
        width=300,
        padding=10,
        border=ft.border.only(right=ft.border.BorderSide(1, ft.Colors.OUTLINE))
    )

    import platform
    import time
    import json
    import os

    # 导出已查看密码的方法
    def export_passwords(e, format_type):
        if not password_cache:
            show_message("没有可导出的密码记录！")
            return
            
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        export_data = []
        for ssid, pwd in password_cache.items():
            export_data.append({
                "SSID": ssid,
                "Password": pwd
            })
            
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        
        try:
            if format_type == "json":
                filename = f"wifi_passwords_{timestamp}.json"
                filepath = os.path.join(desktop_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                    
            elif format_type == "doc":
                # 这里简单输出为带有 markdown 格式的纯文本，伪装成 doc 方便阅读
                filename = f"wifi_passwords_{timestamp}.doc"
                filepath = os.path.join(desktop_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("Wi-Fi 密码导出记录\n")
                    f.write("="*30 + "\n\n")
                    for item in export_data:
                        f.write(f"Wi-Fi 名称 (SSID): {item['SSID']}\n")
                        f.write(f"Wi-Fi 密码: {item['Password']}\n")
                        f.write("-" * 30 + "\n")
                        
            show_message(f"导出成功：{filepath}")
        except Exception as ex:
            show_message(f"导出失败: {str(ex)}")

    export_json_item = ft.PopupMenuItem(
        content=ft.Text("导出密码 (JSON)"),
        icon=ft.Icons.DATA_OBJECT,
        tooltip="导出已查看过的密码为 JSON",
        on_click=lambda e: export_passwords(e, "json"),
    )
    export_doc_item = ft.PopupMenuItem(
        content=ft.Text("导出密码 (DOC)"),
        icon=ft.Icons.DESCRIPTION,
        tooltip="导出已查看过的密码为 DOC(文本)",
        on_click=lambda e: export_passwords(e, "doc"),
    )

    # 顶部菜单栏配置
    page.appbar = ft.AppBar(
        leading=ft.Icon(ft.Icons.WIFI_LOCK),
        leading_width=40,
        title=ft.Text("跨平台 Wi-Fi 管理器"),
        center_title=False,
        bgcolor=ft.Colors.SURFACE,
        actions=[
            ft.PopupMenuButton(
                icon=ft.Icons.MENU,
                tooltip="导出",
                items=[
                    export_json_item,
                    export_doc_item,
                ]
            ),
        ],
    )

    def get_os_info():
        system = platform.system()
        release = platform.release()
        version = platform.version()
        if system == "Darwin":
            mac_ver = platform.mac_ver()[0]
            return f"macOS {mac_ver}"
        elif system == "Windows":
            return f"Windows {release}"
        elif system == "Linux":
            return "Linux"
        return f"{system} {release}"

    os_info_text = ft.Text(f"当前系统: {get_os_info()}", color=ft.Colors.GREY_500, size=12)
    time_text = ft.Text("", color=ft.Colors.GREY_500, size=12)
    version_text = ft.Text("v1.0.0", color=ft.Colors.GREY_500, size=12)

    def update_time():
        while True:
            time_text.value = time.strftime("%Y-%m-%d %H:%M:%S")
            page.update()
            time.sleep(1)

    import threading
    threading.Thread(target=update_time, daemon=True).start()

    footer_row = ft.Row(
        [os_info_text, ft.Container(expand=True), time_text, ft.Container(width=20), version_text],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # 主布局
    main_row = ft.Row(
        controls=[
            list_container,
            details_container
        ],
        expand=True,
    )

    page.add(
        ft.Column(
            [
                main_row,
                ft.Divider(height=1),
                footer_row
            ],
            expand=True
        )
    )
    refresh_wifi()

if __name__ == "__main__":
    ft.app(target=main)
