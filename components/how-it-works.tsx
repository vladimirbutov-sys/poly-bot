import { Search, Filter, ArrowRightLeft } from 'lucide-react'

const steps = [
  {
    number: '01',
    title: 'Сканирование',
    description: 'Непрерывный мониторинг рынков Polymarket в поиске высоковероятных исходов каждые 5 минут',
    icon: Search,
  },
  {
    number: '02',
    title: 'Фильтрация',
    description: '13 фильтров отсекают coin-flip, низколиквидные и рискованные рынки. Диапазон входа: 96–99.5¢',
    icon: Filter,
  },
  {
    number: '03',
    title: 'Вход и выход',
    description: 'Лимитный ордер на покупку. После резолюции рынка — автоматический вывод выигрыша',
    icon: ArrowRightLeft,
  },
]

export function HowItWorks() {
  return (
    <section className="py-12">
      <h2 className="text-xl font-semibold text-white mb-8 flex items-center gap-3">
        <span className="w-1 h-6 bg-gradient-to-b from-blue-500 to-cyan-400 rounded-full" />
        Как это работает
      </h2>
      <div className="relative">
        <div className="absolute top-1/2 left-0 right-0 hidden lg:block">
          <div className="mx-[15%] dotted-connector" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {steps.map((step, index) => {
            const Icon = step.icon
            return (
              <div key={step.number} className="glass-card p-6 relative group hover:bg-white/[0.08] transition-all duration-300">
                <div className="flex items-center gap-4 mb-4">
                  <span className="text-5xl font-mono font-bold gradient-text opacity-80">{step.number}</span>
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-400/20 flex items-center justify-center text-cyan-400 group-hover:from-blue-500/30 group-hover:to-cyan-400/30 transition-all">
                    <Icon className="w-6 h-6" />
                  </div>
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{step.title}</h3>
                <p className="text-sm text-white/50 leading-relaxed">{step.description}</p>
                {index < steps.length - 1 && (
                  <div className="absolute -right-3 top-1/2 -translate-y-1/2 hidden lg:flex w-6 h-6 items-center justify-center text-cyan-400/50 z-10">
                    <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
                      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
