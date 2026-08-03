import { chromium } from "playwright";
import * as path from "path";

const ART_DIR = "C:/Users/pc/.gemini/antigravity-ide/brain/8f5d610a-6413-4b84-9438-fd814429c559";

async function testPage(page, urlPath, pageName) {
  console.log(`Navigating to ${urlPath}...`);
  await page.goto(`http://localhost:5173${urlPath}`);
  await page.waitForLoadState("networkidle");
  
  // Test Desktop View
  console.log(`Testing desktop viewport for ${pageName}...`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(ART_DIR, `${pageName}-desktop.png`) });
  
  // Test Tablet View
  console.log(`Testing tablet viewport for ${pageName}...`);
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(ART_DIR, `${pageName}-tablet.png`) });
  
  // Test Mobile View
  console.log(`Testing mobile viewport for ${pageName}...`);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(ART_DIR, `${pageName}-mobile.png`) });
}

async function run() {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    // 1. Navigate to Auth Page and Log In
    console.log("Navigating to login page...");
    await page.goto("http://localhost:5173/");
    await page.waitForLoadState("networkidle");
    
    console.log("Filling login credentials...");
    await page.fill('input[type="email"]', "tom@acme.com");
    await page.fill('input[type="password"]', "Datacon123!");
    
    console.log("Submitting login form...");
    await Promise.all([
      page.click('button[type="submit"]'),
      page.waitForNavigation({ url: "**/chat", timeout: 15000 })
    ]);
    console.log("Successfully logged in!");
    
    // 2. Test chat page layout & responsiveness
    await testPage(page, "/chat", "chat-page");
    
    // 3. Navigate to Settings -> Users and test responsiveness
    await testPage(page, "/settings/users", "users-page");
    
    // 4. Test User Modal popup on mobile size to verify fit/alignment
    console.log("Testing Modal layout on Mobile viewport...");
    await page.setViewportSize({ width: 375, height: 667 });
    
    // Click '+ Create user' button to open modal
    const inviteButton = page.locator('button:has-text("+ Create user")');
    if (await inviteButton.count() > 0) {
      console.log("Clicking '+ Create user' button to open Modal...");
      await inviteButton.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(ART_DIR, "modal-mobile.png") });
      console.log("Create User modal screenshot captured on mobile!");
    } else {
      console.log("Warning: '+ Create user' button not found, searching other buttons...");
      const buttons = await page.locator('button').allTextContents();
      console.log("Available buttons:", buttons);
    }
    
  } catch (error) {
    console.error("Error running Playwright tests:", error);
  } finally {
    await browser.close();
    console.log("Browser closed. Testing complete!");
  }
}

run();
