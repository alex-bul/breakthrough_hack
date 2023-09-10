import React, { Component } from 'react';
import { Container, Row, Col, InputGroup, FormControl, ListGroup, Badge, Card, Button, Spinner, Form } from 'react-bootstrap';

class App extends Component {
  state = {
    searchValue: '',
    cartList: [],
    filteredProducts: [],
    nextBestOffer: false
  };
  timerId = null;

  handleSearchInputChange = (event) => {
    clearTimeout(this.timerId);
    this.setState({ searchValue: event.target.value });
    if (event.target.value) {
      this.timerId = setTimeout(() => {
        fetch(`http://127.0.0.1:8080/search?q=${event.target.value}`)
          .then((response) => response.json())
          .then((data) => {
            this.setState({ filteredProducts: data });
          })
          .catch((error) => {
            console.error('Ошибка при выполнении запроса:', error);
          });
      }, 500);
    }
    else {
      this.setState({ filteredProducts: [] });

    }

  };

  handleProductClick = (product) => {
    if (!this.state.cartList.includes(product)) {
      this.setState((prevState) => ({
        cartList: [...prevState.cartList, product],
        filteredProducts: [],
        nextBestOffer: null
      }), () => this.updateNextBestOffer());

    }
  };

  updateNextBestOffer = () => {
    if (this.state.cartList.length) {
      fetch('http://127.0.0.1:8080/best_offer', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(
          this.state.cartList
        ),
      })
        .then(response => response.json())
        .then(result => {
          this.setState({ nextBestOffer: result });

        })
        .catch(error => {
          // обработка ошибок
          console.error('Error:', error);
        });
    }
    else {
      this.setState({ nextBestOffer: false });
    }
  }

  handleRemoveFromCart = (product) => {
    this.setState((prevState) => ({
      cartList: prevState.cartList.filter(item => item.id !== product.id)
    }), () => this.updateNextBestOffer());
  };

  handleClearCart = () => {
    this.setState((prevState) => ({
      cartList: []
    }), () => this.updateNextBestOffer());
  };

  handleFormSubmit = (e) => {
    e.preventDefault();
    e.target.reset();
  };

  render() {
    const { searchValue, cartList, filteredProducts, nextBestOffer } = this.state;

    // const filteredProducts = searchValue ? productList.filter(product =>
    //   product.name.toLowerCase().startsWith(searchValue.toLowerCase())
    // ) : [];

    return (
      <Container className="mt-5">
        <Row className="justify-content-center">
          <Col md={6}>
            <InputGroup className="" onClick={this.handleSearchInputChange}>
              <FormControl
                placeholder="Поиск"
                value={searchValue}
                onChange={this.handleSearchInputChange}
              />
            </InputGroup>
            {filteredProducts.length > 0 && (
              <ListGroup className="mb-3" md={6} style={{ position: 'absolute', zIndex: 100, maxWidth: '400px' }}>
                {filteredProducts.map(product => (
                  <ListGroup.Item
                    action
                    key={product.id}
                    onClick={() => this.handleProductClick(product)}
                  >
                    {product.name}
                  </ListGroup.Item>
                ))}
              </ListGroup>
            )}
            <Card className='mt-3 bg-success text-white' style={{ cursor: 'pointer' }} onClick={!nextBestOffer ? () => { } : () => this.handleProductClick(nextBestOffer)}>
              <Card.Body>
                {nextBestOffer === false ? <Card.Text><b>Наполните корзину, чтобы появился рекомендованный товар</b></Card.Text> : (!nextBestOffer ? <Spinner animation="border" variant="white" size="sm" /> :
                  <Card.Text><b>Рекомендация: {nextBestOffer.name}</b></Card.Text>)}
              </Card.Body>
            </Card>
            <Card className='mt-3'>
              <Card.Body>
                <Card.Title>Корзина товаров</Card.Title>
                {cartList.length === 0 ? (
                  <Badge variant="warning">Корзина пуста</Badge>
                ) : <Badge variant="danger" className='bg-danger mb-2' style={{ cursor: 'pointer' }} onClick={this.handleClearCart}>Очистить корзину</Badge>}
                {cartList.map(product => (
                  <Card key={product.id} className="mb-2">
                    <Card.Body className='d-flex justify-content-between align-items-center'>
                      <Card.Text className='mb-0' style={{ maxWidth: '350px' }}>{product.name}</Card.Text>
                      <Button variant="danger" size="sm" onClick={() => this.handleRemoveFromCart(product)}>
                        &times;
                      </Button>
                    </Card.Body>
                  </Card>
                ))}
              </Card.Body>
            </Card>
            <Card className='mt-3'>
              <Card.Body>
                <Card.Title>Загрузка датасета</Card.Title>

                <Form onSubmit={this.handleFormSubmit}>
                  <Form.Group controlId="fileUpload">
                    <Form.Label>Выберите файл:</Form.Label>
                    <Form.Control type="file" />
                  </Form.Group>

                  <Button type="submit" className='mt-2'>Отправить</Button>
                </Form>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    );
  }
}

export default App;