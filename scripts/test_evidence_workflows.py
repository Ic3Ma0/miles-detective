"""Evidence contracts through the existing offline command-line interfaces."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent


def event(**changes):
    row = dict(kind='event', id='EV1', title='合成事件', summary='合成记载',
               status='corroborated', date_precision='unknown', scope='main',
               evidence_type='mixed', source_ids=['S1', 'S2'])
    return {**row, **changes}


def claim(**changes):
    row = dict(kind='claim', id='C1', text='合成记载', status='corroborated',
               evidence=[dict(source_id=s, relation='supports', locator='第1行') for s in ['S1', 'S2']])
    return {**row, **changes}


def materials(access='full_text', group='g2', url='https://example.org/b'):
    rows = [dict(kind='search', id='Q1', engine='fixture', queries=['合成'], raw_path='raw.txt')]
    for i in (1, 2):
        rows.append(dict(kind='visit', id=f'V{i}', url=f'https://example.org/{i}',
                         method='fixture', outcome='content', detail='合成', raw_path='raw.txt'))
        rows.append(dict(kind='source', id=f'S{i}', title='合成',
                         url='https://example.org/a' if i == 1 else url,
                         voice='other', form='original', identity='confirmed', limitation='合成',
                         access='full_text' if i == 1 else access, visit_ids=[f'V{i}'],
                         discovery_ids=['Q1'], same_source_group='g1' if i == 1 else group))
    return rows


class EvidenceWorkflows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.case = Path(self.tmp.name)
        (self.case/'records.jsonl').write_text('')
        (self.case/'raw.txt').write_text('合成材料')

    def run_cli(self, script, *args, payload=None, ok=True):
        proc = subprocess.run([sys.executable, str(SCRIPTS/script), *map(str, args)],
                              input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0 if ok else 2, proc.stdout + proc.stderr)
        return proc

    def append(self, rows, ok=True, case=None):
        return self.run_cli('research_log.py', 'append', case or self.case, '--input', '-', payload=rows, ok=ok)

    def test_search_summary_cannot_corroborate_event_and_rejection_is_atomic(self):
        self.append(materials('search_only'))
        before = (self.case/'records.jsonl').read_bytes()
        self.append(event(), ok=False)
        self.assertEqual((self.case/'records.jsonl').read_bytes(), before)
        self.append(claim(), ok=False)

    def test_evidence_matrix_matches_claims_and_events(self):
        for name, access, group, url, accepted in [
            ('valid', 'full_text', 'g2', 'https://example.org/b', True),
            ('metadata', 'metadata_only', 'g2', 'https://example.org/b', True),
            ('unretrieved', 'unretrieved', 'g2', 'https://example.org/b', False),
            ('same_url', 'full_text', 'g2', 'https://example.org/a', False),
            ('same_group', 'full_text', 'g1', 'https://example.org/b', False),
            ('missing_group', 'full_text', None, 'https://example.org/b', False),
        ]:
            for row in [claim(), event()]:
                with self.subTest(name=name, kind=row['kind']):
                    rows = materials(access, group, url)
                    if group is None:
                        rows[-1].pop('same_source_group')
                    self.append(rows + [row], ok=accepted)
                    (self.case/'records.jsonl').write_text('')

    def test_valid_pair_survives_extra_unusable_or_ungrouped_support(self):
        rows = materials()
        extra = {**rows[-1], 'id':'S3', 'url':'https://example.org/c', 'access':'search_only'}
        extra.pop('same_source_group')
        c = claim()
        c['evidence'].append(dict(source_id='S3', relation='supports', locator='摘要'))
        self.append(rows + [extra, c, event(source_ids=['S1','S2','S3'])])
        self.run_cli('research_log.py', 'check', self.case)

    def test_context_and_contradiction_cannot_supply_independent_support(self):
        self.append(materials())
        for relation in ['context', 'contradicts']:
            row = claim()
            row['evidence'][1]['relation'] = relation
            self.append(row, ok=False)

    def test_source_corrections_recheck_both_records_and_preserve_history(self):
        for kind in ['claim','event']:
            for correction in ['search_only','unretrieved','group','visit']:
                with self.subTest(kind=kind, correction=correction):
                    (self.case/'records.jsonl').write_text('')
                    rows = materials()
                    row = claim() if kind == 'claim' else event()
                    self.append(rows + [row])
                    before = (self.case/'records.jsonl').read_bytes()
                    changed = dict(rows[-1])
                    if correction == 'group':
                        changed['same_source_group'] = 'g1'
                    elif correction == 'visit':
                        changed = {**rows[-2], 'outcome':'shell', 'correction_reason':'分类更正'}
                    else:
                        changed['access'] = correction
                    self.append(changed, ok=False)
                    self.assertEqual((self.case/'records.jsonl').read_bytes(), before)
                    self.run_cli('research_log.py', 'check', self.case)
                    updates = [changed]
                    if correction == 'visit':
                        updates.append({**rows[-1], 'access':'unretrieved'})
                    updates.append({**row,'status':'unverified'})
                    self.append(updates)
                    self.assertTrue((self.case/'records.jsonl').read_bytes().startswith(before))
                    self.run_cli('research_log.py', 'check', self.case)

    def test_documented_records_lose_all_support_after_correction(self):
        for row in [claim(status='documented_statement'), event(status='documented', source_ids=[], sources=[{'id':'S1','file':'page.txt'}])]:
            with self.subTest(kind=row['kind']):
                (self.case/'records.jsonl').write_text('')
                rows = materials()
                self.append(rows + [row])
                before = (self.case/'records.jsonl').read_bytes()
                self.append([{**r,'access':'unretrieved'} for r in rows if r['kind']=='source'], ok=False)
                self.assertEqual((self.case/'records.jsonl').read_bytes(), before)

    def test_known_locator_cannot_override_source_group_or_access(self):
        self.append(materials('search_only'))
        for locators in [
            [{'id':'S1','group':'g1'}, {'source_id':'S2','group':'g2'}],
            [{'id':'S1','group':'invented'}, {'source_id':'S2','group':'g2'}],
            [{'id':'S1','group':'g1'}, {'source_id':'S1','group':'g2'}],
        ]:
            self.append(event(source_ids=[], sources=locators), ok=False)
        self.append(event(status='documented', source_ids=[], sources=[{'id':'S2','file':'page.txt'}]), ok=False)

    def standalone(self, row, ok=True, wrapped=False):
        path = self.case/'events.json'
        path.write_text(json.dumps({'events':[row]} if wrapped else [row]))
        return self.run_cli('check_events.py', path, ok=ok)

    def test_standalone_keeps_lightweight_forms_and_reports_limits(self):
        for wrapped in [True, False]:
            output = self.standalone(event(source_ids=[], sources=[{'file':'a.txt','group':'a'},{'file':'b.txt','group':'b'}]), wrapped=wrapped)
            self.assertIn('结构与声明检查通过', output.stdout)
            self.assertIn('来源取得情况、真实独立性与实际支持关系未核验', output.stdout)
        self.standalone(event(source_ids=['S1','S2'], source_groups={'S1':'a','S2':'b'}))
        self.standalone(event(status='documented', source_ids=[], sources=[{'file':'a.txt'}]))

    def test_standalone_rejects_duplicate_aliases_and_conflicting_groups(self):
        for locators in [
            [{'id':'S1','group':'a'}, {'source_id':'S1','group':'b'}],
            [{'file':'a.txt','group':'a'}, {'file':'./a.txt','group':'b'}],
            [{'id':'S1','file':'a.txt','group':'a'}, {'file':'a.txt','group':'b'}],
            [{'id':'S1','group':'a'}, {'id':'S2','group':'a'}],
            [{'id':'S1','group':'a'}, {'id':'S2'}],
        ]:
            with self.subTest(locators=locators):
                proc = self.standalone(event(source_ids=[], sources=locators), ok=False)
                self.assertIn('EV1', proc.stderr)

    def make_shard(self, sid, rows):
        path = self.case/'shards'/sid
        path.mkdir(parents=True)
        (path/'records.jsonl').write_text('')
        (path/'raw.txt').write_text('合成原件')
        (path/'shard.json').write_text(json.dumps(dict(id=sid, family=sid)))
        self.append(rows, case=path)
        return path

    def test_merge_valid_shards_recalculates_groups_and_preserves_report(self):
        # s00 knows A and B are one origin. s01 independently labels A/B;
        # its C shares B's group, so the A/C pair also loses independence.
        self.make_shard('s00', materials(group='g1'))
        rows = materials()
        rows += [{**rows[-1], 'id':'S3', 'url':'https://example.org/c'}]
        c = claim()
        c['evidence'][1]['source_id'] = 'S3'
        e = event(source_ids=[], sources=[{'id':'S1','group':'g1','file':'a.txt'},
                                         {'source_id':'S3','group':'g2','file':'c.txt'}])
        self.make_shard('s01', rows + [c, e])
        self.run_cli('research_log.py', 'merge', self.case, '--dry-run')
        self.assertEqual((self.case/'records.jsonl').read_bytes(), b'')
        self.assertFalse((self.case/'merge-report.json').exists())
        self.run_cli('research_log.py', 'merge', self.case)
        merged = [json.loads(line) for line in (self.case/'records.jsonl').read_text().splitlines()]
        result = {r['kind']:r for r in merged if r['kind'] in ['event','claim']}
        self.assertEqual(result['event']['status'], 'documented')
        self.assertEqual(result['claim']['status'], 'documented_statement')
        report = json.loads((self.case/'merge-report.json').read_text())
        self.assertEqual({r['id'] for r in report['corroborated_downgraded']}, {r['id'] for r in result.values()})
        self.assertTrue(all(r['reason'] for r in report['corroborated_downgraded']))
        self.assertTrue(result['event']['sources'][0]['file'].startswith('shards/s01/'))
        self.run_cli('research_log.py', 'check', self.case)
        before = (self.case/'records.jsonl').read_bytes()
        self.run_cli('research_log.py', 'merge', self.case, ok=False)
        self.assertEqual((self.case/'records.jsonl').read_bytes(), before)

    def test_merge_rejects_invalid_input_instead_of_downgrading(self):
        shard = self.make_shard('s01', materials('search_only'))
        with (shard/'records.jsonl').open('a') as f:
            f.write(json.dumps(event())+'\n')
        self.run_cli('research_log.py', 'merge', self.case, ok=False)
        self.assertEqual((self.case/'records.jsonl').read_bytes(), b'')

    def test_file_alias_cannot_restore_known_unavailable_support(self):
        self.append(materials('search_only'))
        self.append(event(source_ids=[], sources=[{'id':'S1','group':'g1'},
            {'id':'S2','file':'b.txt','group':'g2'}, {'file':'./b.txt','group':'g2'}]), ok=False)

    def test_check_rejects_stale_event_when_ledger_is_edited(self):
        self.append(materials() + [event()])
        path = self.case/'records.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if row['id']=='S2':
                row['access']='search_only'
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        before = path.read_bytes()
        self.run_cli('research_log.py', 'check', self.case, ok=False)
        self.assertEqual(path.read_bytes(), before)

    def test_standalone_preserves_documented_claim_reference(self):
        self.standalone(event(status='documented', source_ids=[], claim_ids=['C1']))

    def test_duplicate_url_annotation_cannot_create_an_independent_group(self):
        for row in [claim(), event(source_ids=['S1','S2','S3'])]:
            with self.subTest(kind=row['kind']):
                (self.case/'records.jsonl').write_text('')
                rows = materials(group='g1')
                alias = {**rows[2], 'id':'S3', 'same_source_group':'other'}
                if row['kind']=='claim':
                    row['evidence'].append(dict(source_id='S3', relation='supports', locator='第1行'))
                self.append(rows + [alias, row], ok=False)

    def test_unreferenced_known_url_alias_still_constrains_independence(self):
        for row in [claim(), event()]:
            with self.subTest(kind=row['kind']):
                (self.case/'records.jsonl').write_text('')
                rows = materials()
                alias = {**rows[2], 'id':'S3', 'same_source_group':'g2'}
                self.append(rows + [alias, row], ok=False)

    def test_merge_unknown_locator_ids_cannot_collide_with_global_ids(self):
        self.make_shard('s00', materials())
        self.make_shard('s01', [event(status='documented', source_ids=[],
            sources=[{'id':'S01','file':'unknown.txt','group':'unknown'}])])
        self.run_cli('research_log.py', 'merge', self.case)
        self.run_cli('research_log.py', 'check', self.case)
        rows = [json.loads(line) for line in (self.case/'records.jsonl').read_text().splitlines()]
        e = next(row for row in rows if row['kind']=='event')
        self.assertEqual(e['sources'][0]['id'], 's01/S01')

    def test_malformed_optional_locator_components_give_diagnostics(self):
        for field, value in [('source_id',42), ('id',{}), ('file',42)]:
            with self.subTest(field=field):
                row = event(status='documented', source_ids=[], sources=[{'file':'a.txt','id':'external',field:value}])
                proc = self.standalone(row, ok=False)
                self.assertIn('EV1', proc.stderr)
                self.assertNotIn('Traceback', proc.stderr)
