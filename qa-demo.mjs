// Demo: admin searches the seeded student directory across several criteria.
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
  await page.waitForTimeout(1200);

  const read = async () => page.evaluate(() => ({
    count: document.querySelector('#admin-count').textContent.trim(),
    students: [...document.querySelectorAll('#student-directory .student-result')].map(card => ({
      name: card.querySelector('h3').textContent,
      reg: card.querySelector('.student-dept').textContent,
      details: card.querySelector('.student-data').textContent,
    })),
  }));

  out['1_fullDirectory'] = await read();

  await page.fill('#admin-skill-search', 'python cloud');
  await page.selectOption('#admin-skill-type', 'software');
  await page.waitForTimeout(1200);
  out['2_software_python_cloud'] = await read();

  await page.selectOption('#admin-skill-type', 'hardware');
  await page.fill('#admin-skill-search', 'arduino');
  await page.waitForTimeout(1200);
  out['3_hardware_arduino'] = await read();

  await page.selectOption('#admin-skill-type', 'hardware');
  await page.fill('#admin-skill-search', 'vlsi embedded');
  await page.waitForTimeout(1200);
  out['4_hardware_vlsi_embedded'] = await read();

  await page.selectOption('#admin-skill-type', 'all');
  await page.fill('#admin-skill-search', 'python');
  await page.fill('#admin-min-cgpa', '8');
  await page.waitForTimeout(1200);
  out['5_python_minCgpa8'] = await read();

  await page.fill('#admin-skill-search', '');
  await page.fill('#admin-min-cgpa', '');
  await page.waitForTimeout(1200);
  out['6_reset'] = await read();

  return out;
}
