/** Shared calendar event change signal.

ThreadSidebar 中的迷你日历和 CalendarView 页面各自持有自己的 events 数组。
删除/添加日程后，CalendarView 更新了本地数据但侧边栏不知道，导致红点不消失。

通过这个信号量，两边可以同步刷新。
 */
import { ref } from 'vue'

/**
 * 日历数据变更信号。每次 CRUD 操作后 +1，让所有组件重新加载。
 */
export const calendarChangeSignal = ref(0)

export function notifyCalendarChange() {
  calendarChangeSignal.value++
}
