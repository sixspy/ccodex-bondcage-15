export const auditViewTemplate = `
<section class="panel">
  <h2>审计争用</h2>
  <p class="hint">写动作落审计；后到争用只记 contention，不写业务。</p>
  <p class="hint">
    违约出金门闸（纪要 {{ gateMeta.locked_at || '2026-11-22' }} 锁死 · {{ gateMeta.basis || '甲路径·状态门闸拒写零增' }}）：
    拒写审计 <code>breach_outflow_reject</code>、偏航 <code>gate_deviation</code>、争用痕 <code>争用</code> 均在此页可查；判定与其余四页同源。
  </p>
  <div class="grid-2">
    <div>
      <h3>门闸事件</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>事件</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="g in gateEvents" :key="'ge-'+g.id">
            <td>{{ g.created_at }}</td>
            <td>{{ g.actor }}</td>
            <td><span class="badge fail">{{ g.action }}</span></td>
            <td>{{ g.target }}</td>
            <td><code style="font-size:11px">{{ g.payload }}</code></td>
          </tr>
          <tr v-if="!gateEvents.length">
            <td colspan="5" class="hint">暂无门闸事件</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">审计</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>动作</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="a in audits" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.actor }}</td>
            <td>{{ a.action }}</td>
            <td>{{ a.target }}</td>
            <td><code style="font-size:11px">{{ a.payload }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>持锁</h3>
      <table>
        <thead><tr><th>键</th><th>持有者</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="l in locks" :key="l.lock_key">
            <td>{{ l.lock_key }}</td>
            <td>{{ l.holder }}</td>
            <td>{{ l.acquired_at }}</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">争用</h3>
      <table>
        <thead><tr><th>时间</th><th>键</th><th>人</th><th>动作</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="c in contention" :key="c.id">
            <td>{{ c.created_at }}</td>
            <td>{{ c.lock_key }}</td>
            <td>{{ c.actor }}</td>
            <td>{{ c.action }}</td>
            <td>{{ c.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
