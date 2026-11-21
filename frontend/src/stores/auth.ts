import { acceptHMRUpdate, defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { http, readStoredToken, unwrap, writeStoredToken } from '@/lib/http'

export interface AuthUser {
  id: number
  email: string
  nickname: string
  role: 'user' | 'operator' | 'admin'
  balance: string
  frozen: string
  usageMultiplier: string
}

export interface AuthSessionResponse {
  accessToken: string
  tokenType: string
  expiresIn: number
  user: AuthUser
}

export interface CreditBalanceResponse {
  balance: string
  frozen: string
  usageMultiplier: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(readStoredToken())
  const user = ref<AuthUser | null>(null)
  const loading = ref(false)
  let hydratePromise: Promise<AuthUser | null> | null = null

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isStaff = computed(() => user.value?.role === 'admin' || user.value?.role === 'operator')
  const numericBalance = computed(() => {
    if (!user.value) return null
    const parsed = Number(user.value.balance)
    return Number.isFinite(parsed) ? parsed : 0
  })

  function applySession(session: AuthSessionResponse) {
    token.value = session.accessToken
    user.value = session.user
    writeStoredToken(session.accessToken)
  }

  function clearSession() {
    token.value = null
    user.value = null
    writeStoredToken(null)
  }

  async function hydrate() {
    if (hydratePromise) return hydratePromise
    const currentToken = token.value ?? readStoredToken()
    if (!currentToken) {
      user.value = null
      return null
    }
    token.value = currentToken
    loading.value = true
    hydratePromise = (async () => {
      try {
        const me = await unwrap<AuthUser>(http.get('/users/me', { skipUnauthorizedHandler: true }))
        user.value = me
        return me
      } catch {
        clearSession()
        return null
      } finally {
        loading.value = false
        hydratePromise = null
      }
    })()
    return hydratePromise
  }

  async function register(email: string, password: string, nickname = '') {
    const session = await unwrap<AuthSessionResponse>(
      http.post('/auth/register', { email, password, nickname }),
    )
    applySession(session)
    return session.user
  }

  async function login(email: string, password: string) {
    const session = await unwrap<AuthSessionResponse>(
      http.post('/auth/login', { email, password }),
    )
    applySession(session)
    return session.user
  }

  async function logout() {
    try {
      if (token.value) await http.post('/auth/logout')
    } catch {
      // Ignore network errors when revoking session.
    } finally {
      clearSession()
    }
  }

  async function refreshBalance() {
    if (!token.value) return
    try {
      const data = await unwrap<CreditBalanceResponse>(http.get('/credits/balance'))
      if (user.value) {
        user.value = {
          ...user.value,
          balance: data.balance,
          frozen: data.frozen,
          usageMultiplier: data.usageMultiplier,
        }
      }
    } catch {
      // Keep last known balance on transient network hiccup.
    }
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    isAdmin,
    isStaff,
    numericBalance,
    hydrate,
    register,
    login,
    logout,
    refreshBalance,
    clearSession,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useAuthStore, import.meta.hot))
}
