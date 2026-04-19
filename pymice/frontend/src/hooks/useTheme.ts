import { useEffect, useState, useCallback } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'pymice-theme'

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches
  return prefersLight ? 'light' : 'dark'
}

function applyThemeClass(theme: Theme) {
  const root = document.documentElement
  if (theme === 'dark') root.classList.add('dark')
  else root.classList.remove('dark')
}

export function useTheme(): { theme: Theme; toggleTheme: () => void; setTheme: (t: Theme) => void } {
  const [theme, setThemeState] = useState<Theme>(() => {
    const initial = readInitialTheme()
    if (typeof window !== 'undefined') applyThemeClass(initial)
    return initial
  })

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    applyThemeClass(next)
    window.localStorage.setItem(STORAGE_KEY, next)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark')
  }, [theme, setTheme])

  useEffect(() => {
    // Track OS preference only while the user hasn't made an explicit choice.
    const mql = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = (e: MediaQueryListEvent) => {
      if (window.localStorage.getItem(STORAGE_KEY)) return
      const next: Theme = e.matches ? 'light' : 'dark'
      setThemeState(next)
      applyThemeClass(next)
    }
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return { theme, toggleTheme, setTheme }
}
