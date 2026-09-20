import os
import re
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

def run_crawler(selected_period: str):
    """Automates Banco Inter web portal to download checking account and card statements."""
    os.makedirs("./downloads", exist_ok=True)

    # Extract days and compute start date (DD/MM/YYYY)
    days_to_subtract = int(re.search(r'\d+', selected_period).group())
    today = datetime.now()
    start_date_dt = today - timedelta(days=days_to_subtract)
    start_date = start_date_dt.strftime("%d/%m/%Y")

    with sync_playwright() as p:
        print("[*] Launching browser in widget mode (QR Code login)...")
        
        # 1. Configure Chromium as an app window
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--app=https://contadigital.inter.co',  # Removes address bar and tabs
                '--window-size=1280,800',
                '--window-position=300,100'
            ]
        )
        
        # 2. Match viewport to window dimensions
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        page.goto("https://contadigital.inter.co")
        
        print("\n[!] Please scan the QR Code on screen with your Banco Inter app.")
        
        try:
            # Wait for authenticated dashboard
            page.wait_for_selector('text="Conta Digital"', timeout=90000) 
            print("[+] Login detected successfully!")

            # Inject animated privacy curtain
            print("[*] Applying privacy overlay. Starting extraction animation...")
            curtain_js = """
            // Step 1: Inject animation keyframes
            let style = document.createElement('style');
            style.innerHTML = `
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            `;
            document.head.appendChild(style);

            // Step 2: Create blocking overlay
            let overlay = document.createElement('div');
            overlay.style.position = 'fixed';
            overlay.style.top = '0';
            overlay.style.left = '0';
            overlay.style.width = '100vw';
            overlay.style.height = '100vh';
            overlay.style.backgroundColor = '#0a0a0a'; 
            overlay.style.zIndex = '99999999';
            overlay.style.display = 'flex';
            overlay.style.alignItems = 'center';
            overlay.style.justifyContent = 'center';
            overlay.style.color = '#00FF00';
            overlay.style.fontFamily = 'monospace';
            overlay.style.pointerEvents = 'none'; // Allows clicks to pass through to underlying DOM
            
            // Step 3: Add spinner and status label
            overlay.innerHTML = `
                <div style="display:flex; flex-direction:column; align-items:center;">
                    <div style="width: 60px; height: 60px; border: 5px solid #1a1a1a; border-top: 5px solid #00FF00; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 25px;"></div>
                    <div style="font-size: 24px; animation: pulse 2s infinite;">[ STATUS: EXTRACTING FINANCIAL DATA ]</div>
                    <div style="font-size: 14px; color: #555; margin-top: 15px;">Bot operation in progress. Please do not close this window...</div>
                </div>
            `;
            document.body.appendChild(overlay);
            """
            page.evaluate(curtain_js)

            print("[*] Waiting for dashboard components to stabilize (5s)...")
            page.wait_for_timeout(5000)

            print("[*] Navigating to account statement...")

            # Focus visible account menu
            account_menu = page.locator("text='Conta Digital'").locator("visible=true").first
            account_menu.hover()

            # 1. Navigate via top menu
            page.locator("text='Extrato' >> visible=true").first.click()

            # 2. Open date filter
            print(f"[*] Applying statement filter: {selected_period}...")
            page.get_by_test_id("filterChipsDates").click()
            page.wait_for_timeout(1000)

            # 3. Select requested period
            page.click(f"text='{selected_period}'", timeout=45000)

            # 4. Apply filter
            page.click("text='Filtrar'")

            page.wait_for_timeout(3000)
            
            print("[*] Clicking Export...")
            page.click("text='Exportar'") 

            print("[*] Selecting CSV format...")
            page.click("text='CSV'")

            print("[*] Confirming export and downloading...")
            with page.expect_download() as download_info:
                page.click("text='Continuar'")
                
            download = download_info.value

            file_name = selected_period.replace(' ', '')
            account_path = f"./downloads/extrato_conta_{file_name}.csv"
            download.save_as(account_path)
            
            print(f"[+] Checking account statement saved to: {account_path}")

            print("[*] Dismissing leftover modals...")
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # 2. Credit card invoice extraction attempt (isolated to protect statement download)
            try:
                print("\n[*] [2/2] Navigating to Credit Cards section...")
                page.click("text='Cartões'")
                page.wait_for_timeout(3000)
                
                print("[*] Opening 'Ver mais' menu...")
                page.click("text='Ver mais'", timeout=10000)
                page.wait_for_timeout(2000)

                print("[*] Accessing Credit Cards Statement...")
                page.locator("text='Extrato' >> visible=true").first.click(timeout=15000)
                page.wait_for_timeout(2000)

                print("[*] Opening datepicker...")
                page.get_by_text("A partir de").click()
                page.wait_for_timeout(1000)
                
                # Navigate calendar months if needed
                months_back = (today.year - start_date_dt.year) * 12 + (today.month - start_date_dt.month)
                
                if months_back > 0:
                    print(f"[*] Navigating back {months_back} month(s) in calendar...")
                    for _ in range(months_back):
                        page.locator("div[data-testid='modal-content-wrapper'] button").first.click()
                        page.wait_for_timeout(500)
                
                calendar_day = str(start_date_dt.day)
                print(f"[*] Selecting day {calendar_day} in calendar...")
                page.locator(f'text="{calendar_day}" >> visible=true').first.click()
                page.wait_for_timeout(1000)
                
                print("[*] Applying date filter...")
                page.click("text='Aplicar'", force=True)

                print("[*] Waiting for card statement table to load (3s)...")
                page.wait_for_timeout(3000)

                print("[*] Downloading card statement CSV...")
                with page.expect_download() as download_cartao_info:
                    page.locator("text='Exportar' >> visible=true").last.click(force=True)
                  
                card_path = f"./downloads/fatura_cartao_{file_name}.csv"
                download_cartao_info.value.save_as(card_path)
                print(f"[+] Credit card statement saved to: {card_path}")

            except Exception as e_card:
                print("\n[!] WARNING: Could not export card invoice via web UI.")
                print(f"[!] Detail: {e_card}")
                print("[!] Recommendation: If you have the invoice in PDF, place it in the 'Faturas_Inter' folder.")
                print("[*] Pipeline will proceed with the checking account statement already downloaded.")
        
        except Exception as e:
            print(f"\n[X] Critical error during browser automation: {e}")
            sys.exit(1)

        finally:
            print("[*] Closing browser session securely...")
            browser.close()

if __name__ == "__main__":
    user_choice = input()
    run_crawler(user_choice)