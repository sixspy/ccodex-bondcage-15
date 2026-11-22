export const attestViewTemplate = `
<section class="panel">
  <h2>履约核验</h2>
  <p class="hint">
    对已冻结笼给出通过或违约结论；同一笼代不得改口。通过后可解笼，违约后只允许罚没方向出金。
    违约出金门闸（纪要 {{ gateMeta.locked_at || '2026-11-22' }} 锁死 · {{ gateMeta.basis || '甲路径·状态门闸拒写零增' }}）：
    违约态在解笼写口直接拒写零增，不得改判通过。
  </p>
  <div class="grid-2">
    <div>
      <div class="form-row">
        <div>
          <label>笼</label>
          <select v-model.number="attestForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in frozenCages" :key="c.id" :value="c.id">
              {{ c.cage_code }} · {{ fmt(c.available) }} · 代{{ c.generation }}
            </option>
          </select>
        </div>
        <div>
          <label>结论</label>
          <select v-model="attestForm.outcome">
            <option>通过</option>
            <option>违约</option>
          </select>
        </div>
        <div style="grid-column:1/-1">
          <label>证据摘要</label>
          <textarea v-model="attestForm.evidence" placeholder="验收单号 / 违约说明"></textarea>
        </div>
      </div>
      <div class="actions">
        <button class="ok" @click="doAttest">提交核验</button>
      </div>
    </div>
    <div>
      <h3>门闸同源判定</h3>
      <table>
        <thead><tr><th>笼</th><th>状态</th><th>核验口径</th><th>出金方向</th></tr></thead>
        <tbody>
          <tr v-for="g in gateRows" :key="'ag-'+g.cage_id">
            <td>{{ g.cage_code }}</td>
            <td><span class="badge" :class="g.breach?'fail':(g.outcome?'pass':'frozen')">{{ g.status }}</span></td>
            <td>{{ g.outcome || '待核验' }}</td>
            <td><span class="badge" :class="g.breach?'fail':'pass'">{{ g.outflow }}</span></td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">核验记录</h3>
      <table>
        <thead>
          <tr><th>时间</th><th>笼</th><th>结论</th><th>笼代</th><th>核验员</th><th>证据</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in attestations" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.cage_code }}</td>
            <td><span class="badge" :class="a.outcome==='通过'?'pass':'fail'">{{ a.outcome }}</span></td>
            <td>{{ a.attest_gen }}</td>
            <td>{{ a.officer }}</td>
            <td>{{ a.evidence }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
