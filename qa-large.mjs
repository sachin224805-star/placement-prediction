// Verify the directory handles the full 1000-student dataset.
export default async function run(page, ui) {
  const out = {};
  const snap = await ui.snapshot();
  const adminTab = snap.match(/(@e\d+) button "Placement cell"/)?.[1];
  await ui.click(adminTab);
  await page.waitForTimeout(200);
  await page.fill('#admin-username', 'placementadmin');
  await page.fill('#admin-password', 'Sahrdaya@2026');
  await page.click('#admin-login-form .login-submit');
  await page.waitForFunction(() => document.body.classList.contains('admin'), null, { timeout: 5000 });
  await page.waitForTimeout(2500);

  const read = async () => page.evaluate(() => ({
    count: document.querySelector('#admin-count').textContent.trim(),
    cards: document.querySelectorAll('#student-directory .student-result').length,
    first: document.querySelector('#student-directory .student-result h3')?.textContent || null,
  }));

  const t0 = Date.now();
  out.fullDirectory = await read();
  out.fullDirectoryMs = Date.now() - t0;
  out.pager = await page.evaluate(() => {
    const nav = document.querySelector('#student-directory .directory-empty');
    return nav ? nav.textContent : null;
  });

  // Click Next to confirm pagination moves to the second page.
  await page.getByRole('button', { name: 'Next' }).click();
  await page.waitForTimeout(500);
  out.page2 = await page.evaluate(() => ({
    cards: document.querySelectorAll('#student-directory .student-result').length,
    first: document.querySelector('#student-directory .student-result h3').textContent,
    pager: document.querySelector('#student-directory .directory-empty').textContent,
  }));

  await page.fill('#admin-skill-search', 'python');
  await page.selectOption('#admin-skill-type', 'software');
  await page.waitForTimeout(2500);
  out.softwarePython = await read();

  await page.selectOption('#admin-skill-type', 'software');
  await page.fill('#admin-skill-search', 'java spring');
  await page.waitForTimeout(2500);
  out.softwareJavaSpring = await read();

  await page.selectOption('#admin-skill-type', 'software');
  await page.fill('#admin-skill-search', 'python');
  await page.fill('#admin-min-cgpa', '9');
  await page.waitForTimeout(2500);
  out.pythonMinCgpa9 = await read();

  return out;
}
