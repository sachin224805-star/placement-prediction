const express = require('express');
const cors = require('cors');
const session = require('express-session');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const app = express();
const PORT = process.env.PORT || 5000;
const BASE = __dirname;
const uploadDir = path.join(BASE, 'uploads');
const profileFile = path.join(BASE, 'student_profiles.json');
fs.mkdirSync(uploadDir, { recursive: true });
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '2mb' }));
app.use(session({ secret: process.env.FLASK_SECRET_KEY || 'change-this-local-placement-secret', resave: false, saveUninitialized: false, cookie: { maxAge: 86400000 } }));
app.use(express.static(BASE));

const upload = multer({
  dest: uploadDir,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => cb(null, /\.(pdf|png|jpe?g)$/i.test(file.originalname))
});
const DEPT = { CE: 0, CSE: 1, ECE: 2, EEE: 3, IT: 4, ME: 5 };
const subjects = [['ai','AI'],['ml','Machine Learning'],['cn','Computer Networks'],['cd','Compiler Design'],['web','Web Technology'],['mp','Mini Project']];
const readProfiles = () => { try { return JSON.parse(fs.readFileSync(profileFile, 'utf8')); } catch { return {}; } };
const writeProfiles = data => fs.writeFileSync(profileFile, JSON.stringify(data, null, 2));
const list = value => Array.isArray(value) ? value.map(String).map(s => s.trim()).filter(Boolean).slice(0, 50) : [];
const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

app.get('/companies', (_req, res) => res.sendFile(path.join(BASE, 'company_jobs.json')));
app.post('/upload-certificate', upload.single('certificate'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'Only PDF, PNG, JPG, and JPEG certificate files are supported.' });
  const ext = path.extname(req.file.originalname).toLowerCase();
  const stored = `${crypto.randomUUID()}${ext}`;
  fs.renameSync(req.file.path, path.join(uploadDir, stored));
  res.status(201).json({ name: req.file.originalname, url: `/uploads/${stored}` });
});
app.use('/uploads', express.static(uploadDir));

app.post('/student-profile', (req, res) => {
  const name = String(req.body.name || '').trim();
  const registerNumber = String(req.body.registerNumber || '').trim().toUpperCase();
  if (!name || !registerNumber) return res.status(400).json({ error: 'Student name and register number are required.' });
  const profiles = readProfiles();
  profiles[registerNumber] = { ...req.body, name, registerNumber, software: list(req.body.software), hardware: list(req.body.hardware), certificates: list(req.body.certificates), certificateFiles: list((req.body.certificateFiles || []).map(x => x.name || x)), updatedAt: new Date().toISOString() };
  writeProfiles(profiles);
  res.json({ saved: true });
});
app.post('/admin/login', (req, res) => {
  const username = process.env.PLACEMENT_ADMIN_USERNAME || 'placementadmin';
  const password = process.env.PLACEMENT_ADMIN_PASSWORD || 'Sahrdaya@2026';
  if (req.body.username !== username || req.body.password !== password) return res.status(401).json({ error: 'Invalid admin credentials.' });
  req.session.admin = true; res.json({ authenticated: true });
});
app.post('/admin/logout', (req, res) => { req.session.destroy(() => res.json({ logged_out: true })); });
app.get('/admin/students', (req, res) => {
  if (!req.session.admin) return res.status(401).json({ error: 'Admin sign-in required.' });
  const terms = String(req.query.skills || '').toLowerCase().split(/\s+/).filter(Boolean);
  const type = ['software','hardware','certificates'].includes(req.query.skillType) ? req.query.skillType : null;
  const min = req.query.minimumCgpa === undefined ? null : number(req.query.minimumCgpa);
  const students = Object.values(readProfiles()).filter(p => {
    const skills = type ? (p[type] || []) : [...(p.software || []), ...(p.hardware || []), ...(p.certificates || [])];
    const searchable = [...skills, p.appliedCompany || ''].join(' ').toLowerCase();
    return terms.every(t => searchable.includes(t)) && (min === null || number(p.cgpa) >= min);
  }).sort((a,b) => String(a.name).localeCompare(String(b.name)));
  res.json({ students });
});

function tips(d, backlog, placement) {
  const out = [];
  if (backlog) { if (number(d.attendance) < 75) out.push({type:'danger',text:'Boost attendance above 75% to reduce backlog exposure.'}); if (number(d.study) < 4) out.push({type:'warning',text:'Increase daily study time to at least 4 to 5 hours.'}); if (number(d.cgpa) < 6.5) out.push({type:'warning',text:'Focus on core subjects to move your CGPA above 6.5.'}); }
  if (!placement) { if (number(d.communication) < 6) out.push({type:'info',text:'Build communication skills through public speaking practice and feedback.'}); if (number(d.technical) < 6 || number(d.coding) < 6) out.push({type:'info',text:'Create a consistent technical and coding practice routine.'}); if (!number(d.projects)) out.push({type:'info',text:'Build one or two practical projects to strengthen your resume.'}); if (d.internship === 'No') out.push({type:'info',text:'Pursue an internship to add relevant experience to your profile.'}); }
  return out.length ? out : [{type:'success',text:'Maintain your performance and continue upskilling in your chosen area.'},{type:'success',text:'Your profile supports applying to more selective opportunities.'}];
}
app.post('/predict', (req, res) => {
  const d = req.body || {};
  const required = ['department','semester','study','attendance','internal','cgpa','communication','technical','coding','aptitude','projects','certifications','internship'];
  if (!required.every(k => d[k] !== undefined)) return res.status(400).json({ error: 'Complete all profile fields before running an assessment.' });
  const backlogProb = Math.max(3, Math.min(97, 20 + (75-number(d.attendance))*0.9 + (6.5-number(d.cgpa))*13 + (4-number(d.study))*4 + (55-number(d.internal))*0.35));
  const placementProb = Math.max(3, Math.min(97, (number(d.cgpa)-5)*10 + number(d.communication)*3 + number(d.technical)*4 + number(d.coding)*4 + number(d.aptitude)*0.18 + number(d.projects)*5 + number(d.certifications)*3 + (d.internship === 'Yes' ? 10 : 0) - 25));
  const backlog = backlogProb >= 50 ? 1 : 0, placement = placementProb >= 55 ? 1 : 0;
  const resultSubjects = subjects.map(([key,name]) => { const s=(d.subjects||{})[key]||{}; const internal=Math.max(0,Math.min(40,number(s.internal,d.internal))); const hours=Math.max(0,Math.min(15,number(s.hours,d.study))); const risk=backlog===1 && internal<24; return {key,name,internal,hours,at_risk:risk,probability:risk?85:15}; });
  res.json({ backlog, placement, backlog_probability:+backlogProb.toFixed(1), placement_probability:+placementProb.toFixed(1), subjects:resultSubjects, predicted_backlog_count:resultSubjects.filter(s=>s.at_risk).length, tips:tips(d,backlog,placement) });
});
app.get('*', (_req,res) => res.sendFile(path.join(BASE,'index.html')));
app.listen(PORT, () => console.log(`Node server running at http://localhost:${PORT}`));
