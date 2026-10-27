import React from 'react';
import { Alert, Container, Button } from 'react-bootstrap';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    console.error('[ErrorBoundary]', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <Container className="mt-4">
          <Alert variant="danger">
            <Alert.Heading>Something crashed rendering this page</Alert.Heading>
            <p className="mb-1"><strong>{this.state.error.name}:</strong> {this.state.error.message}</p>
            {this.state.info?.componentStack && (
              <details className="mt-2">
                <summary>Component stack</summary>
                <pre style={{ fontSize: '0.8rem', maxHeight: 300, overflow: 'auto' }}>
                  {this.state.info.componentStack}
                </pre>
              </details>
            )}
            <Button
              variant="outline-danger"
              size="sm"
              className="mt-2"
              onClick={() => this.setState({ error: null, info: null })}
            >
              Try again
            </Button>
          </Alert>
        </Container>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
