import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return this.props.fallback ?? (
        <div style={{ padding: 24, color: 'red' }}>
          <b>Ошибка инициализации:</b> {this.state.error.message}
          <br />
          <small>Откройте приложение через Telegram.</small>
        </div>
      )
    }
    return this.props.children
  }
}
