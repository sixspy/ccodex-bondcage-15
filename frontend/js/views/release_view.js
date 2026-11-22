export const releaseViewTemplate = `
<section class="panel">
  <h2>解笼拨付</h2>
  <p class="hint">
    仅核验通过的笼可拨付。违约出金门闸（纪要 {{ gateMeta.locked_at || '2026-11-22' }} 锁死 ·
    {{ gateMeta.basis || '甲路径·状态门闸拒写零增' }}）：违约笼禁止解笼拨付，只允许罚没方向出金；
    写口遇违约直接拒写零增并记拒写审计。
  </p>
  <div class="grid-2">
    <div>
      <div class="form-row">
        <div>
          <label>通过态笼</label>
          <select v-model.number="releaseForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in releasableCages" :key="c.id" :value="c.id">
              {{ c.cage_code }} · 可用 {{ fmt(c.available) }}
            </option>
          </select>
        </div>
        <div>
          <label>金额（空=全额）</label>
          <input type="number" v-model.number="releaseForm.amount" min="0" step="1000" placeholder="全额"/>
        </div>
        <div>
          <label>收款方（空=受益人）</label>
          <input v-model="releaseForm.payee"/>
        </div>
      </div>
      <div class="actions">
        <button class="ok" @click="doRelease">解笼拨付</button>
      </div>
      <div v-if="releaseForm.cage_id" class="gate-note">
        <span class="badge pass">门闸放行</span>
        {{ (gateOf(releaseForm.cage_id) || {}).reason || '通过口径可拨付' }}
      </div>
      <div class="gate-block" v-if="breachGates.length">
        <h3>门闸拦截 · 违约笼禁止拨付</h3>
        <table>
          <thead><tr><th>笼</th><th>状态</th><th>可用</th><th>出金方向</th><th>口径</th></tr></thead>
          <tbody>
            <tr v-for="g in breachGates" :key="'blk-'+g.cage_id">
              <td>{{ g.cage_code }}</td>
              <td><span class="badge fail">{{ g.status }}</span></td>
              <td>{{ fmt(g.available) }}</td>
              <td><span class="badge fail">{{ g.outflow }}</span></td>
              <td>{{ g.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div>
      <table>
        <thead>
          <tr><th>凭证</th><th>笼</th><th>金额</th><th>收款方</th><th>笼代</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in releases" :key="r.id">
            <td>{{ r.release_ref }}</td>
            <td>{{ r.cage_code }}</td>
            <td>{{ fmt(r.amount) }}</td>
            <td>{{ r.payee }}</td>
            <td>{{ r.cage_generation }}</td>
            <td>{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
